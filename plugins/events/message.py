import logging
import logging
import pathlib
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, Message, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import FileSizeLimit
from telegram.ext import ContextTypes, filters, MessageHandler, CallbackQueryHandler

import decorators
import utilities
from config import config
from constants import Group, TempDataKey
from database.models import Chat, Event, PartiesMessage
from database.queries import events, parties_messages, chats
from emojis import Emoji
from ext.filters import ChatFilter, Filter
from plugins.events.common import (
    add_event_message_metadata,
    parse_message_text,
    parse_message_entities,
    drop_events_cache
)

logger = logging.getLogger(__name__)


async def download_event_media(message: Message):
    if not message.photo and not message.video and not message.animation:
        logger.debug(f"no media to backup")
        return

    if not message.photo and message.effective_attachment.file_size > FileSizeLimit.FILESIZE_DOWNLOAD:
        logger.info(f"file too large: {message.effective_attachment.file_size} bytes")
        return

    if not message.edit_date:
        file_name = f"{message.message_id}"
    else:
        edit_timestamp = int(message.edit_date.timestamp())
        file_name = f"{message.message_id}_edit_{edit_timestamp}"

    if message.photo:
        file_name = f"{file_name}.jpg"
    elif message.video or message.animation:
        file_name = f"{file_name}.mp4"

    file_path = pathlib.Path("events_data") / file_name

    logger.info(f"downloading to {file_path}...")
    if message.photo:
        new_file = await message.effective_attachment[-1].get_file()
    else:
        new_file = await message.effective_attachment.get_file()

    await new_file.download_to_drive(file_path)


async def backup_event_media(update: Update, event: Optional[Event] = None):
    # edited_messages: do not download the media if it was not modified
    if update.edited_message and event:
        m = update.edited_message
        new_file_unique_id = m.photo[-1].file_unique_id if m.photo else m.effective_attachment.file_unique_id
        if new_file_unique_id == event.media_file_unique_id:
            logger.debug(
                f"edited event message: file_unique_id ({new_file_unique_id}) didn't change, skipping media download")
            return False

    try:
        await download_event_media(update.effective_message)
        return True
    except Exception as e:
        logger.error(f"error while trying to download media: {e}", exc_info=True)
        return False


def date_notifications_reply_markup(event_chat_id: int, event_message_id: int):
    keyboard = [[
        InlineKeyboardButton(f"{Emoji.BELL_MUTED} silenzia", callback_data=f"mutemsg:{event_chat_id}:{event_message_id}"),
        InlineKeyboardButton(f"{Emoji.EXCLAMATION_MARK} non una festa", callback_data=f"notaparty:{event_chat_id}:{event_message_id}")
    ]]

    return InlineKeyboardMarkup(keyboard)


async def notify_event_validity(
        session: Session,
        event: Event,
        bot: Bot,
        is_edited_message: bool,
        was_valid_before_parsing: bool,
        is_valid_after_parsing: bool
):
    logger.debug(f"is_edited_message: {is_edited_message}; "
                 f"was_valid_before_parsing: {was_valid_before_parsing}; "
                 f"is_valid_after_parsing: {is_valid_after_parsing}; "
                 f"Event.send_validity_notifications: {event.send_validity_notifications}")

    if not event.send_validity_notifications:
        return

    staff_chat = chats.get_chat(session, Chat.is_staff_chat)
    if not staff_chat:
        return

    reply_markup = date_notifications_reply_markup(event.chat_id, event.message_id)
    if not was_valid_before_parsing and is_valid_after_parsing:
        logger.info("event wasn't valid but is now valid after message edit: deleting staff notification")
        # text = (f"{event.message_link_html('Questa festa')} non aveva una data ed è stata modificata, "
        #         f"adesso è apposto {Emoji.DONE}")
        # await bot.send_message(staff_chat.chat_id, text, reply_markup=reply_markup)
        if event.validity_notification_chat_id and event.validity_notification_message_id:
            # delete if now ok
            await utilities.delete_messages_by_id_safe(bot, event.validity_notification_chat_id, event.validity_notification_message_id)
    elif not is_valid_after_parsing and not is_edited_message:
        # do not notify invalid edited messages, as they have been notified already
        logger.info("new event is not valid, notifying chat")
        text = (f"Non sono riuscito ad identificare la data di \"{event.title_link_html()}\", e non è stata "
                f"taggata come #soon (può essere che la data sia scritta in modo strano e vada modificata)")
        sent_message = await bot.send_message(staff_chat.chat_id, text, reply_markup=reply_markup)
        event.save_validity_notification_message(sent_message)
    elif was_valid_before_parsing and not is_valid_after_parsing:
        logger.info("event is no longer valid after message edit")
        text = (f"\"{event.title_link_html()}\" aveva una data ma non è più possibile identificarla "
                f"dopo che il messaggio è stato modificato :(")
        sent_message = await bot.send_message(staff_chat.chat_id, text, reply_markup=reply_markup)
        event.save_validity_notification_message(sent_message)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_album_message_no_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"events chat message (album message but no text) {utilities.log(update)}")

    # we need to catch updates that do not have a text/caption, but that are part of an album

    if config.settings.backup_events:
        await backup_event_media(update)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_event_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"events chat message update {utilities.log(update)}")

    # chat_id = update.effective_message.forward_from_chat.id
    # message_id = update.effective_message.forward_from_message_id

    chat_id = update.effective_chat.id
    message_id = update.effective_message.message_id

    event: Event = events.get_or_create(session, chat_id, message_id)

    # mark 'was_valid' as true if the Event originates from a *new* post (no 'edit_date')
    # we need this flag to notify the admins when an invalid event becomes valid, and we do not notify
    # them when a new event is posted, because for new events, Event.is_valid() will
    # of course return false (text hasn't been parsed yet)
    # Also, for an event to be valid, the dates must *not* come from the hashtag
    is_edited_message = bool(update.effective_message.edit_date)
    was_valid_before_parsing = event.is_valid_from_parsing() or not is_edited_message
    had_hashtags = bool(event.get_hashtags())

    add_event_message_metadata(update.effective_message, event)

    # we need to parse the message text *before* parsing the hashtags (entities) list because if no date is found
    # we reset the strat and end date, but then they should be populated again if a month hashtag is found
    # if we do the opposite, if no date is found in the message text, the dates from the month hashtag will be
    # reset even if they are valid
    parse_message_text(update.effective_message.text or update.effective_message.caption, event)
    parse_message_entities(update.effective_message, event)

    logger.info(f"parsed event: {event}")

    if event.not_a_party:
        # if the event is marked as 'not a party', we stop here
        # we parse the medtadata & text anyway because that flag might be turned to false: in that case,
        # the message data should be up-to-date
        # anyway we can avoid to drop the cache, set the UPDATE_PARTIES_MESSAGE flag, and send validity notifications
        logger.debug("event is marked as \"not a party\": nothing to do, returning")
        return

    is_valid_after_parsing = event.is_valid_from_parsing()
    has_hashtags = bool(event.get_hashtags())

    logger.info("setting flag to signal that the parties message list should be updated...")
    context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True

    logger.info("dropping events cache...")
    drop_events_cache(context)

    session.commit()

    if config.settings.notify_events_validity:
        await notify_event_validity(
            session=session,
            event=event,
            bot=context.bot,
            is_edited_message=is_edited_message,
            was_valid_before_parsing=was_valid_before_parsing,
            is_valid_after_parsing=is_valid_after_parsing
        )

    if config.settings.backup_events:
        await backup_event_media(update, event)


@decorators.catch_exception(silent=True)
@decorators.pass_session()
async def on_linked_group_event_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"discussion group: channel message update {utilities.log(update)}")

    channel_chat_id = update.message.sender_chat.id
    channel_message_id = update.message.forward_from_message_id
    
    event: Event = events.get_or_create(session, channel_chat_id, channel_message_id, create_if_missing=False)
    if not event:
        logger.warning(f"no Event was found for message {channel_message_id} in chat {channel_chat_id}")
    else:
        logger.info("Event: saving discussion group's post info...")
        event.save_discussion_group_message(update.effective_message)

        logger.info("setting flag to signal that the parties message list should be updated...")
        context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True
    
        # make sure to drop the event cache so new commands will have updated info
        logger.info("dropping events cache...")
        drop_events_cache(context)

        # no need to try to get a PartiesMessage if an Event for this message was found
        return
    
    parties_message: Optional[PartiesMessage] = parties_messages.get_parties_message(session, channel_chat_id, channel_message_id)
    if not parties_message:
        logger.warning(f"no PartiesMessage was found for message {channel_message_id} in chat {channel_chat_id}")
    else:
        logger.info("PartiesMessage: saving discussion group's post info...")
        parties_message.save_discussion_group_message(update.effective_message)


@decorators.catch_exception(silent=True)
@decorators.pass_session()
async def on_events_chat_pinned_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"events chat: pinned message {utilities.log(update)}")

    # we check whether the pinned message is a parties message: in that case, we delete the service message
    chat_id = update.effective_chat.id
    message_id = update.effective_message.pinned_message.message_id

    parties_message: Optional[PartiesMessage] = parties_messages.get_parties_message(session, chat_id, message_id)
    if not parties_message:
        logger.warning(f"no PartiesMessage was found for pinned message {message_id} in chat {chat_id}")
        return

    logger.info("deleting \"pinned message\" service message...")
    await utilities.delete_messages_safe(update.effective_message)


@decorators.catch_exception()
@decorators.pass_session()
async def on_disable_notifications_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"disable notifications button {utilities.log(update)}")
    chat_id = int(context.matches[0].group("chat_id"))
    message_id = int(context.matches[0].group("message_id"))

    # we add also the current message's message_id because multiple messages for the same Event have the
    # same callback_data, and if we use the same user_data key for taps coming from different messages,
    # we can't distinguish when the user tapped on a message instead of another
    tap_key = f"mute:{update.effective_message.message_id}:{chat_id}:{message_id}"

    if TempDataKey.MUTE_EVENT_MESSAGE_BUTTON_ONCE not in context.user_data:
        context.user_data[TempDataKey.MUTE_EVENT_MESSAGE_BUTTON_ONCE] = {}

    if tap_key not in context.user_data[TempDataKey.MUTE_EVENT_MESSAGE_BUTTON_ONCE]:
        logger.info(f"first time tap for key {tap_key}, showing alert...")
        await update.callback_query.answer(
            f"Così facendo non verranno più inviate notifiche quando il messaggio in questione viene modificato. "
            f"Usa di nuovo il tasto \"{Emoji.BELL_MUTED} silenzia\" per confermare",
            show_alert=True
        )
        context.user_data[TempDataKey.MUTE_EVENT_MESSAGE_BUTTON_ONCE][tap_key] = True
        return

    event: Event = events.get_or_create(session, chat_id, message_id, create_if_missing=False)
    if not event:
        logger.info(f"no Event found for tap key {tap_key}")
        await update.callback_query.answer("Ooops, qualcosa è andato storto. "
                                           "Impossibile trovare il messaggio nel database", show_alert=True)
        await update.callback_query.edit_message_reply_markup(reply_markup=None)

        # pop the key, no reason to keep it
        context.user_data[TempDataKey.MUTE_EVENT_MESSAGE_BUTTON_ONCE].pop(tap_key, None)

        return

    if not event.send_validity_notifications:
        logger.info("notifications were already muted")  # just remove the inline markup

        await update.callback_query.edit_message_reply_markup(reply_markup=None)
        context.user_data[TempDataKey.MUTE_EVENT_MESSAGE_BUTTON_ONCE].pop(tap_key, None)
        return

    event.send_validity_notifications = False
    session.commit()

    user_mention_html = update.effective_user.mention_html(utilities.escape_html(update.effective_user.full_name))
    new_text = f"{update.effective_message.text_html}\n\n<b><i>{user_mention_html} ha silenziato le notifiche per questo messaggio</i></b>"
    await update.callback_query.answer("Non verranno più inviate notifiche riguardo al messaggio in questione", show_alert=True)
    edited_message = await update.callback_query.edit_message_text(new_text, reply_markup=None)
    event.save_validity_notification_message(edited_message)
    # await update.effective_message.delete()

    context.user_data[TempDataKey.MUTE_EVENT_MESSAGE_BUTTON_ONCE].pop(tap_key, None)


@decorators.catch_exception()
@decorators.pass_session()
async def on_not_a_party_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"not a party button {utilities.log(update)}")
    chat_id = int(context.matches[0].group("chat_id"))
    message_id = int(context.matches[0].group("message_id"))

    # see this same comment in 'on_disable_notifications_button()'
    tap_key = f"notaparty:{update.effective_message.message_id}:{chat_id}:{message_id}"

    if TempDataKey.NOT_A_PARTY_MESSAGE_BUTTON_ONCE not in context.user_data:
        context.user_data[TempDataKey.NOT_A_PARTY_MESSAGE_BUTTON_ONCE] = {}

    if tap_key not in context.user_data[TempDataKey.NOT_A_PARTY_MESSAGE_BUTTON_ONCE]:
        logger.info(f"first time tap for key {tap_key}, showing alert...")
        await update.callback_query.answer(
            f"Usa questo tasto se il post nel canale non fa riferimento ad una festa.\n"
            f"In questo modo non verranno più inviate notifiche riguardo la data.\n"
            f"Usa nuovamente questo tasto per confermare",
            show_alert=True
        )
        context.user_data[TempDataKey.NOT_A_PARTY_MESSAGE_BUTTON_ONCE][tap_key] = True
        return

    event: Event = events.get_or_create(session, chat_id, message_id, create_if_missing=False)
    if not event:
        logger.info(f"no Event found for tap key {tap_key}")
        await update.callback_query.answer("Ooops, qualcosa è andato storto. "
                                           "Impossibile trovare il messaggio nel database", show_alert=True)
        await update.callback_query.edit_message_reply_markup(reply_markup=None)

        # pop the key, no reason to keep it
        context.user_data[TempDataKey.NOT_A_PARTY_MESSAGE_BUTTON_ONCE].pop(tap_key, None)

        return

    if event.not_a_party:
        logger.info("event was already marked a not a party")  # just remove the inline markup

        context.user_data[TempDataKey.NOT_A_PARTY_MESSAGE_BUTTON_ONCE].pop(tap_key, None)
        await update.effective_message.delete()
        return

    event.not_a_party = True
    session.commit()

    await update.callback_query.answer(
        "Ok, non tratterò questo post come fosse una festa. "
        "Non verranno più inviate notifiche a riguardo",
        show_alert=True
    )
    await update.effective_message.delete()

    context.user_data[TempDataKey.NOT_A_PARTY_MESSAGE_BUTTON_ONCE].pop(tap_key, None)
    

HANDLERS = (
    (MessageHandler(ChatFilter.EVENTS & Filter.WITH_TEXT & Filter.MESSAGE_OR_EDIT, on_event_message), Group.PREPROCESS),
    (MessageHandler(ChatFilter.EVENTS & ~Filter.WITH_TEXT & Filter.ALBUM_MESSAGE & Filter.FLY_MEDIA_DOWNLOAD, on_album_message_no_text), Group.PREPROCESS),
    (MessageHandler(filters.ChatType.GROUPS & ChatFilter.EVENTS_GROUP_POST & filters.UpdateType.MESSAGE & Filter.WITH_TEXT, on_linked_group_event_message), Group.PREPROCESS),
    (MessageHandler(ChatFilter.EVENTS & filters.StatusUpdate.PINNED_MESSAGE, on_events_chat_pinned_message), Group.NORMAL),
    (CallbackQueryHandler(on_disable_notifications_button, rf"mutemsg:(?P<chat_id>-\d+):(?P<message_id>\d+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_not_a_party_button, rf"notaparty:(?P<chat_id>-\d+):(?P<message_id>\d+)$"), Group.NORMAL),
)
