import logging
import logging
import pathlib
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, Message
from telegram.ext import ContextTypes, filters, MessageHandler

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


async def backup_event_media(update: Update, event: Event):
    # edited_messages: do not download the media if it was not modified
    if update.edited_message:
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
    is_edited_message = bool(update.effective_message.edit_date)
    was_valid_before_parsing = event.is_valid() or not is_edited_message

    add_event_message_metadata(update.effective_message, event)

    # we need to parse the message text *before* parsing the hashtags (entities) list because if no date is found
    # we reset the strat and end date, but then they should be populated again if a month hashtag is found
    # if we do the opposite, if no date is found in the message text, the dates from the month hashtag will be
    # reset even if they are valid
    parse_message_text(update.effective_message.text or update.effective_message.caption, event)
    parse_message_entities(update.effective_message, event)

    logger.info(f"parsed event: {event}")

    is_valid_after_parsing = event.is_valid()

    logger.info("setting flag to signal that the parties message list should be updated...")
    context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True

    logger.info("dropping events cache...")
    drop_events_cache(context)

    session.commit()

    if config.settings.notify_events_validity:
        logger.debug(f"is_edited_message: {is_edited_message}; "
                     f"was_valid_before_parsing: {was_valid_before_parsing}; "
                     f"is_valid_after_parsing: {is_valid_after_parsing}")

        staff_chat = chats.get_chat(session, Chat.is_staff_chat)
        if staff_chat:
            if not was_valid_before_parsing and is_valid_after_parsing:
                logger.info("event wasn't valid but is now valid after message edit")
                text = (f"{event.message_link_html('Questa festa')} non aveva una data ed è stata modificata, "
                        f"adesso è apposto {Emoji.DONE}")
                await context.bot.send_message(staff_chat.chat_id, text)
            elif not is_valid_after_parsing and not is_edited_message:
                # do not notify invalid edited messages, as they have been notified already
                logger.info("new event is not valid, notifying chat")
                text = (f"Non sono riuscito ad identificare la data di {event.message_link_html('questa festa')} postata "
                        f"nel canale, e non è stata taggata come #soon (può essere che la data sia scritta in modo strano "
                        f"e vada modificata)")
                await context.bot.send_message(staff_chat.chat_id, text)
            elif was_valid_before_parsing and not is_valid_after_parsing:
                # do not notify invalid edited messages, as they have been notified already
                logger.info("event is no longer valid after message edit")
                text = (f"{event.message_link_html('Questa festa')} aveva una data ma non è più possibile "
                        f"identificarla dopo che il messaggio è stato modificato :(")
                await context.bot.send_message(staff_chat.chat_id, text)

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
        logger.warning(f"no PartiesMessage was found for message {message_id} in chat {chat_id}")
        return

    logger.info("deleting \"pinned message\" service message...")
    await utilities.delete_messages_safe(update.effective_message)
    

HANDLERS = (
    (MessageHandler(ChatFilter.EVENTS & Filter.MESSAGE_OR_EDIT & Filter.WITH_TEXT, on_event_message), Group.PREPROCESS),
    (MessageHandler(filters.ChatType.GROUPS & ChatFilter.EVENTS_GROUP_POST & filters.UpdateType.MESSAGE & Filter.WITH_TEXT, on_linked_group_event_message), Group.PREPROCESS),
    (MessageHandler(ChatFilter.EVENTS & filters.StatusUpdate.PINNED_MESSAGE, on_events_chat_pinned_message), Group.NORMAL),
)
