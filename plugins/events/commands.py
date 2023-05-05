import datetime
import json
import logging
import re
from re import Match
from typing import Optional, Tuple, List, Union

import telegram.constants
from sqlalchemy.orm import Session
from telegram import Update, Message, MessageEntity
from telegram.ext import ContextTypes, filters, MessageHandler, CommandHandler
from telegram.constants import MessageLimit

from ext.filters import ChatFilter
from .common import Filter, parse_message_entities, parse_message_text
from database.models import Chat, Event, EventTypeHashtag, EVENT_TYPE, User, BotSetting, EventType
from database.queries import settings, events, chats
import decorators
import utilities
from constants import BotSettingKey, Group, Regex, REGIONS_DATA, RegionName
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


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/events or /eventsall {utilities.log(update)}")

    all_events = "eventsall" in update.message.text.lower()
    order_by_type = False

    query_filters = []
    if context.args:
        args = [arg.lower() for arg in context.args]
        if "bytype" in args:
            order_by_type = True
        if "legal" in args:
            query_filters.append(Event.event_type == EventType.LEGAL)
        if "free" in args:
            query_filters.append(Event.event_type == EventType.FREE)
        if "other" in args:
            other_types = [EventType.OTHER, EventType.STREET_PARADE]
            query_filters.append(Event.event_type.in_(other_types))
        if "week" in args:
            last_monday = utilities.previous_weekday(weekday=0)
            next_monday = utilities.next_weekday(weekday=0)
            query_filters.extend([Event.start_date >= last_monday, Event.start_date < next_monday])
        if "it" in args or "noit" in args:
            it_regions = [RegionName.ITALIA, RegionName.CENTRO_ITALIA, RegionName.NORD_ITALIA, RegionName.SUD_ITALIA]
            if "it" in args:
                query_filters.append(Event.region.in_(it_regions))
            else:
                query_filters.append(Event.region.not_in(it_regions))
    elif not context.args or "week" not in context.args:
        # no temporal filters -> extract all events > this month
        now = utilities.now()
        query_filters.extend([
            Event.start_year >= now.year,
            Event.start_month >= now.month,
        ])

    events_list: List[Event] = events.get_events(session, filters=query_filters, order_by_type=order_by_type)
    messages_to_send = []
    message_events = []
    for i, event in enumerate(events_list):
        if not event.is_valid():
            logger.info(f"skipping invalid event: {event}")
            continue

        region_icon = ""
        if event.region and event.region in REGIONS_DATA:
            region_icon = REGIONS_DATA[event.region]["emoji"]

        title_escaped = utilities.escape_html(event.event_title)
        if event.canceled:
            title_escaped = f"<s>{title_escaped}</s>"

        # text_line = f"{event.icon()}{region_icon} <b>{title_escaped}</b> ({event.pretty_date()}) • <a href=\"{event.message_link()}\">fly & info</a>"
        text_line = f"{event.icon()}{region_icon} <b><a href=\"{event.message_link()}\">{title_escaped}</a></b> • {event.pretty_date()}"

        if time_to_split(message_events, entities_per_line=2):
            new_message_to_send = "\n".join(message_events)
            messages_to_send.append(new_message_to_send)

            # logger.debug(f"time to split, messages: {len(messages_to_send)}, lines: {len(text_lines)}")
            if not all_events:
                message_events = []  # make sure to empty the list so the last message is not sent
                break

            message_events = [text_line]
        else:
            # logger.debug(f"no time to split, messages: {len(messages_to_send)}, lines: {len(text_lines)}")
            message_events.append(text_line)

    # logger.debug(f"result: {len(messages_to_send)} messages, {len(text_lines)} lines")

    if message_events:
        new_message_to_send = "\n".join(message_events)
        messages_to_send.append(new_message_to_send)

    if not messages_to_send:
        await update.message.reply_text("empty :(")
        return

    total_messages = len(messages_to_send)
    for i, text_to_send in enumerate(messages_to_send):
        logger.debug(f"sending message {i+1}/{total_messages}")
        await update.message.reply_text(text_to_send)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_invalid_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/invalidevents {utilities.log(update)}")

    events_list: List[Event] = events.get_events(session)
    text_lines = []
    for i, event in enumerate(events_list):
        if event.is_valid():
            # logger.info(f"skipping valid event: {event}")
            continue

        text_lines.append(f"{event.event_title} {event.message_link()}")

    await update.message.reply_text("\n".join(text_lines))


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


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_delete_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/delevent {utilities.log(update)}")

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

    # session.delete(event)
    event.deleted = True

    await update.effective_message.reply_text(f"Event deleted ({event_ids_str})")


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_fwd_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/fwd {utilities.log(update)}")

    if "origin_fwd" in context.bot_data:
        context.bot_data.pop("origin_fwd")
        await update.message.reply_text("disabled")
    else:
        context.bot_data["origin_fwd"] = True
        await update.message.reply_text("enabled")


HANDLERS = (
    (CommandHandler(["seteventschat", "sec"], on_set_events_chat_command, filters=Filter.ADMIN_PRIVATE), Group.NORMAL),
    (CommandHandler(["events", "eventsall"], on_events_command, filters=filters.User(config.telegram.admins)), Group.NORMAL),
    (CommandHandler(["invalidevents", "ie"], on_invalid_events_command, filters=Filter.ADMIN_PRIVATE), Group.NORMAL),
    (CommandHandler(["parseevents", "pe"], on_parse_events_command, filters=Filter.ADMIN_PRIVATE), Group.NORMAL),
    (CommandHandler(["delevent", "de"], on_delete_event_command, filters=Filter.ADMIN_PRIVATE), Group.NORMAL),
    (CommandHandler(["fwd"], on_fwd_command, filters=Filter.ADMIN_PRIVATE), Group.NORMAL),
)
