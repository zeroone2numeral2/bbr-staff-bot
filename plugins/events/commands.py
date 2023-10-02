import datetime
import json
import logging
from typing import Optional, List

import telegram.constants
from sqlalchemy import true, false, null
from sqlalchemy.orm import Session
from telegram import Update, Message, InlineKeyboardMarkup, InlineKeyboardButton, Chat as TelegramChat
from telegram.ext import ContextTypes, filters, CommandHandler, CallbackContext, CallbackQueryHandler
from telegram.constants import MessageLimit

from emojis import Emoji, Flag
from ext.filters import Filter
from plugins.events.common import (
    parse_message_entities,
    parse_message_text,
    drop_events_cache,
    add_event_message_metadata,
    extract_query_filters,
    get_all_events_strings_from_db,
    send_events_messages,
    format_event_string, FILTER_DESCRIPTION, ORDER_BY_DESCRIPTION
)
from database.models import Chat, Event, User, BotSetting, EventType
from database.queries import settings, events, chat_members, private_chat_messages
import decorators
import utilities
from constants import BotSettingKey, Group, RegionName, MediaType, MONTHS_IT, TempDataKey, Timeout
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.staff_member()
async def on_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/events {utilities.log(update)}")

    args = context.args if context.args else []
    all_events_strings = get_all_events_strings_from_db(session, args)

    # logger.debug(f"result: {len(messages_to_send)} messages, {len(text_lines)} lines")

    protect_content = not utilities.is_superadmin(update.effective_user)
    await send_events_messages(update.message, all_events_strings, protect_content)


@decorators.catch_exception()
async def on_drop_events_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/dropeventscache {utilities.log(update)}")

    drop_events_cache(context)
    await update.message.reply_text("cache dropped")


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_ban()
async def on_invalid_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/invalidevents {utilities.log(update)}")

    events_list: List[Event] = events.get_events(
        session,
        filters=[Event.soon == false()],
        order_by=[Event.message_id]
    )
    all_events_strings = []
    total_entities_count = 0
    for i, event in enumerate(events_list):
        if event.is_valid():
            continue

        text_line, event_entities_count = format_event_string(event, message_date_instead_of_event_date=True)
        all_events_strings.append(text_line)
        total_entities_count += event_entities_count  # not used yet, find something to do with this

    protect_content = not utilities.is_superadmin(update.effective_user)
    sent_messages = await send_events_messages(update.message, all_events_strings, protect_content)
    private_chat_messages.save(session, sent_messages)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_parse_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/parseevents {utilities.log(update)}")

    events_list: List[Event] = events.get_all_events(session)
    events_count = 0
    for i, event in enumerate(events_list):
        events_count = i + 1
        logger.debug(f"{events_count}. {event}")
        parse_message_text(event.message_text, event)

        if not event.message_json:
            continue

        message_dict = json.loads(event.message_json)
        message = Message.de_json(message_dict, context.bot)
        parse_message_entities(message, event)

    await update.message.reply_text(f"parsed {events_count} db entries")


async def event_from_link(update: Update, context: CallbackContext, session: Session) -> Optional[Event]:
    if not context.args:
        return

    message_link = context.args[0]
    chat_id, message_id = utilities.unpack_message_link(message_link)
    if not chat_id:
        await update.message.reply_text("cannot detect the message link pointing to the event")
        return

    if isinstance(chat_id, str):
        await update.message.reply_text("this command doesn't work with public chats")
        return

    event_ids_str = f"chat id: <code>{chat_id}</code>; message id: <code>{message_id}</code>"

    event: Event = events.get_or_create(session, chat_id, message_id, create_if_missing=False)
    if not event:
        await update.effective_message.reply_text(f"No event saved for this message ({event_ids_str})")
        return

    return event


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.staff_member()
async def on_event_action_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"event action {utilities.log(update)}")

    event: Event = await event_from_link(update, context, session)
    if not event:
        # event_from_link() will also answer the user
        return

    # session.delete(event)
    command = utilities.get_command(update.message.text)
    if command in ("delevent", "de", "deleventmsg", "dem"):
        event.deleted = True
        action = "deleted"
    elif command in ("resevent", "re"):
        event.deleted = False
        action = "restored"
    elif command in ("notparty",):
        event.not_a_party = True
        action = "marked as not a party"
    elif command in ("isparty",):
        event.not_a_party = False
        action = "marked as party"
    else:
        raise ValueError(f"invalid command: {command}")

    event_str, _ = format_event_string(event)
    await update.effective_message.reply_text(f"{event_str}\n\n^event {action}")

    # set the flag and drop the cache always, even when the command is /isparty or /notparty, as the command
    # does not originate from an "invalid date" notification, and the Event might be recognized as a valid party
    logger.info("setting flag to signal that the parties message list should be updated and dropping events cache...")
    context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True
    drop_events_cache(context)

    if command in ("deleventmsg", "dem"):
        deletion_result = await utilities.delete_messages_by_id_safe(context.bot, event.chat_id, event.message_id)
        await update.message.reply_html(f"{event.message_link_html('message')} deleted: {str(deletion_result).lower()}\n"
                                        f"Can delete messages in {event.chat.title}: {str(event.chat.can_delete_messages).lower()})")


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.staff_member()
async def on_getpost_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/getpost {utilities.log(update)}")

    event: Event = await event_from_link(update, context, session)
    if not event:
        await update.message.reply_text("nessuno evento per questo link")
        return

    if not event.media_file_id:
        await update.effective_message.reply_html(f"{event.message_text}")
    else:
        # if no media_type, assume photo
        media_type = event.media_type or MediaType.PHOTO
        await utilities.reply_media(
            message=update.message,
            media_type=media_type,
            file_id=event.media_file_id,
            caption=event.message_text
        )


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_reparse_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/reparse {utilities.log(update)}")

    # two ways for this command to work:
    # 1. it can be used with no argument as an answer to a forwarded channel message, in this case we will
    #    try to get the event from the forwarded message and reparse it
    # 2. it can be used in reply to a message with an argument, that is, the message link of the Event object
    #    this is particularly useful when we need to reparse an event in a channel where content is protected,
    #    so we send to the bot the new "dummy" text and reply to that text with the link of the event to update

    if context.args:
        logger.info("args were passed: get the event from the message link")
        # if the command argument is wrong or no event is found, this function will also reply to the user
        event: Optional[Event] = await event_from_link(update, context, session)
        if not event:
            # event_from_link() already replied to the user, just return
            return
    else:
        if not update.message.reply_to_message.forward_from_chat or update.message.reply_to_message.forward_from_chat.type != TelegramChat.CHANNEL:
            await update.message.reply_html(
                "Rispondi ad un messaggi inoltrato da un canale, oppure ad un messaggio di testo seguito dal link "
                "al messaggio dell'evento"
            )
            return

        chat_id = update.message.reply_to_message.forward_from_chat.id
        message_id = update.message.reply_to_message.forward_from_message_id

        event: Event = events.get_or_create(session, chat_id, message_id)
        if not event:
            await update.message.reply_html(f"No event for <code>{chat_id}</code>/<code>{message_id}</code>")
            return

    message_to_parse: Message = update.message.reply_to_message
    add_event_message_metadata(message_to_parse, event, reparse=True)
    parse_message_entities(message_to_parse, event)
    parse_message_text(message_to_parse.text or message_to_parse.caption, event)

    logger.info(f"re-parsed event: {event}")

    logger.info("setting flag to signal that the parties message list shoudl be updated...")
    context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True

    event_str, _ = format_event_string(event)
    await update.effective_message.reply_text(f"{event_str}\n\n^event re-parsed")

    logger.info("dropping events cache...")
    drop_events_cache(context)

    session.commit()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.staff_member()
async def on_getfilters_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/getfilters {utilities.log(update)}")

    text = "<b>Filtri disponibili:</b>"
    for filter_key, description in FILTER_DESCRIPTION.items():
        text += f"\n<code>{filter_key}</code> ➜ {description}"

    text += "\n\n<b>Filtri ordinamento disponibili:</b>"
    for filter_key, description in ORDER_BY_DESCRIPTION.items():
        text += f"\n<code>{filter_key}</code> ➜ {description}"

    text += (f"\n\nUsa <code>/feste [elenco filtri separati da uno spazio]</code> per filtrare le feste\n"
             f"E' possibile combinare più filtri, i filtri per l'ordinamento verranno applicati nell'ordine in cui "
             f"sono elencati\n\n"
             f"Ad esempio, \"<code>/feste ni or od</code>\" restituirà tutte le feste all'estero (\"ni\"), "
             f"ordinate prima per stato/regione (\"or\") e poi per data (\"od\")")
    await update.message.reply_html(text)


HANDLERS = (
    (CommandHandler(["events", "feste", "e"], on_events_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["invalidevents", "ie"], on_invalid_events_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["delevent", "de", "deleventmsg", "dem"], on_event_action_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["resevent", "re"], on_event_action_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["isparty", "notparty"], on_event_action_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["getpost"], on_getpost_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["getfilters", "gf"], on_getfilters_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["reparse", "rp"], on_reparse_command, filters=filters.REPLY & filters.ChatType.PRIVATE), Group.NORMAL),
    # superadmins
    (CommandHandler(["dropeventscache", "dec"], on_drop_events_cache_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["parseevents", "pe"], on_parse_events_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
