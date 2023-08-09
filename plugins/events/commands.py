import datetime
import json
import logging
import re
from re import Match
from typing import Optional, Tuple, List, Union

import telegram.constants
from sqlalchemy import true, false
from sqlalchemy.orm import Session
from telegram import Update, Message, MessageEntity
from telegram.ext import ContextTypes, filters, MessageHandler, CommandHandler, CallbackContext
from telegram.constants import MessageLimit

from ext.filters import ChatFilter, Filter
from .common import parse_message_entities, parse_message_text
from database.models import Chat, Event, EventTypeHashtag, EVENT_TYPE, User, BotSetting, EventType
from database.queries import settings, events, chats
import decorators
import utilities
from constants import BotSettingKey, Group, Regex, REGIONS_DATA, RegionName, MediaType
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_set_events_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/seteventschat {utilities.log(update)}")

    if not update.message.reply_to_message:
        await update.message.reply_text("Use this command in reply to a forwarded message from the channel")
        return

    if not update.message.reply_to_message.forward_from_chat:
        await update.message.reply_text("Use this command in reply to a forwarded message from the channel")
        return

    chats.get_safe(session, update.message.reply_to_message.forward_from_chat)

    events_chat_id = update.message.reply_to_message.forward_from_chat.id
    events_chat_title = update.message.reply_to_message.forward_from_chat.title

    events_chat_setting: BotSetting = settings.get_or_create(session, BotSettingKey.EVENTS_CHAT_ID)

    ChatFilter.EVENTS.chat_ids = {events_chat_id}

    events_chat_setting.update_value(events_chat_id)

    await update.effective_message.reply_text(f"\"{utilities.escape_html(events_chat_title)}\" has been set "
                                              f"as the events chat (<code>{events_chat_id}</code>)")


def time_to_split(text_lines: List[str], entities_per_line: int) -> bool:
    message_length = len("\n\naggiornato al xx/xx/xxxx xx:xx")
    for line in text_lines:
        message_length += len(line)

    if message_length >= MessageLimit.MAX_TEXT_LENGTH:
        return True

    if len(text_lines) * entities_per_line >= MessageLimit.MESSAGE_ENTITIES:
        return True


def format_event_string(event: Event) -> str:
    region_icon = ""
    if event.region and event.region in REGIONS_DATA:
        region_icon = REGIONS_DATA[event.region]["emoji"]

    if event.event_title:
        title_escaped = utilities.escape_html(event.event_title)
    else:
        title_escaped = "unnamed party"

    if event.canceled:
        title_escaped = f"<s>{title_escaped}</s>"

    # text = f"{event.icon()}{region_icon} <b>{title_escaped}</b> ({event.pretty_date()}) • <a href=\"{event.message_link()}\">fly & info</a>"
    text = f"{event.icon()}{region_icon} <b><a href=\"{event.message_link()}\">{title_escaped}</a></b> • {event.pretty_date()}"

    return text


def split_messages(all_events: List[str], return_after_first_message=False) -> List[str]:
    messages_to_send = []
    next_message_events = []
    for events_string in all_events:
        if time_to_split(next_message_events, entities_per_line=2):
            new_message_to_send = "\n".join(next_message_events)
            messages_to_send.append(new_message_to_send)

            # logger.debug(f"time to split, messages: {len(messages_to_send)}, lines: {len(text_lines)}")
            if return_after_first_message:
                return messages_to_send

            next_message_events = [events_string]
        else:
            # logger.debug(f"no time to split, messages: {len(messages_to_send)}, lines: {len(text_lines)}")
            next_message_events.append(events_string)

    if next_message_events:
        last_message_text = "\n".join(next_message_events)
        messages_to_send.append(last_message_text)

    return messages_to_send


def extract_query_filters(args: List[str]) -> List:
    query_filters = []
    args = [arg.lower() for arg in args]

    # EVENT TYPE
    if "legal" in args:
        # legal = anything that is not a free party
        query_filters.append(Event.event_type != EventType.FREE)
    elif "free" in args:
        query_filters.append(Event.event_type == EventType.FREE)

    # EVENT DATE
    if "week" in args:
        last_monday = utilities.previous_weekday(weekday=0)
        next_monday = utilities.next_weekday(weekday=0)
        query_filters.extend([Event.start_date >= last_monday, Event.start_date < next_monday])
    elif "all" in args:
        # all events >= this month
        now = utilities.now()
        query_filters.extend([
            Event.start_year >= now.year,
            Event.start_month >= now.month,
        ])
    elif "soon" in args:
        query_filters.extend([Event.soon == true()])
    else:
        # this month + next month
        now = utilities.now()
        this_month = now.month
        next_month = now.month + 1 if now.month != 12 else 1

        query_filters.extend([
            Event.start_year >= now.year,
            Event.start_month.in_(this_month, next_month),
        ])

    # EVENT REGION
    it_regions = [RegionName.ITALIA, RegionName.CENTRO_ITALIA, RegionName.NORD_ITALIA, RegionName.SUD_ITALIA]
    if "it" in args:
        query_filters.append(Event.region.in_(it_regions))
    elif "noit" in args:
        query_filters.append(Event.region.not_in(it_regions))

    return query_filters


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/events or /eventsall {utilities.log(update)}")

    args = context.args if context.args else []
    query_filters = extract_query_filters(args)

    events_list: List[Event] = events.get_events(session, filters=query_filters, order_by_type=False)

    all_events_strings = []
    for i, event in enumerate(events_list):
        if not event.is_valid():
            logger.info(f"skipping invalid event: {event}")
            continue

        text_line = format_event_string(event)
        all_events_strings.append(text_line)

    # logger.debug(f"result: {len(messages_to_send)} messages, {len(text_lines)} lines")

    messages_to_send = split_messages(all_events_strings, return_after_first_message=False)

    if not messages_to_send:
        await update.message.reply_text("empty :(")
        return

    total_messages = len(messages_to_send)
    for i, text_to_send in enumerate(messages_to_send):
        logger.debug(f"sending message {i+1}/{total_messages}")
        if i + 1 == total_messages:
            text_to_send += f"\n\nUse /soon for a list of events without a scheduled date"

        await update.message.reply_text(text_to_send)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_invalid_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/invalidevents {utilities.log(update)}")

    events_list: List[Event] = events.get_events(
        session,
        filters=[Event.soon == false()],
        order_by_override=[Event.message_id]
    )
    all_events_strings = []
    for i, event in enumerate(events_list):
        if event.is_valid():
            continue

        text_line = format_event_string(event)
        all_events_strings.append(text_line)

    messages_to_send = split_messages(all_events_strings)

    if not messages_to_send:
        await update.message.reply_text("none")
        return

    total_messages = len(messages_to_send)
    for i, text_to_send in enumerate(messages_to_send):
        logger.debug(f"sending message {i + 1}/{total_messages}")
        await update.message.reply_text(text_to_send)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_soon_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/soon {utilities.log(update)}")

    events_list: List[Event] = events.get_events(
        session,
        filters=[Event.soon == true()],
        order_by_override=[Event.message_id]
    )
    all_events_strings = []
    for i, event in enumerate(events_list):
        text_line = format_event_string(event)
        all_events_strings.append(text_line)

    messages_to_send = split_messages(all_events_strings)

    if not messages_to_send:
        await update.message.reply_text("none")
        return

    total_messages = len(messages_to_send)
    for i, text_to_send in enumerate(messages_to_send):
        logger.debug(f"sending message {i + 1}/{total_messages}")
        await update.message.reply_text(text_to_send)


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
        await update.message.reply_text("cannot detect the message link pointing to the event to delete")
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
async def on_delete_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/delevent {utilities.log(update)}")

    event: Event = await event_from_link(update, context, session)
    if not event:
        return

    # session.delete(event)
    event.deleted = True

    event_str = format_event_string(event)
    await update.effective_message.reply_text(f"{event_str}\n\n^event deleted")


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_getfly_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/getfly {utilities.log(update)}")

    event: Event = await event_from_link(update, context, session)
    if not event:
        return

    event_str = format_event_string(event)

    if not event.media_file_id:
        await update.effective_message.reply_text(f"No file id for {event_str}")
        return

    await update.effective_message.reply_text(f"fly for {event_str}")

    # if no media_type, assume photo
    media_type = event.media_type or MediaType.PHOTO
    await utilities.reply_media(message=update.message, media_type=media_type, file_id=event.media_file_id)


HANDLERS = (
    (CommandHandler(["seteventschat", "sec"], on_set_events_chat_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["events", "eventi"], on_events_command, filters=filters.User(config.telegram.admins)), Group.NORMAL),
    (CommandHandler(["invalidevents", "ie"], on_invalid_events_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["soon"], on_soon_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["parseevents", "pe"], on_parse_events_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["delevent", "de"], on_delete_event_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["fly", "getfly"], on_getfly_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
