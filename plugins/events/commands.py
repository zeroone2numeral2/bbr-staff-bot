import datetime
import json
import logging
import re
from re import Match
from typing import Optional, Tuple, List, Union

import telegram.constants
from sqlalchemy import true, false
from sqlalchemy.orm import Session
from telegram import Update, Message, MessageEntity, InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser
from telegram.ext import ContextTypes, filters, MessageHandler, CommandHandler, CallbackContext, CallbackQueryHandler
from telegram.constants import MessageLimit

from emojis import Emoji, Flag
from ext.filters import ChatFilter, Filter
from .common import parse_message_entities, parse_message_text, drop_events_cache
from database.models import Chat, Event, EventTypeHashtag, EVENT_TYPE, User, BotSetting, EventType
from database.queries import settings, events, chats, chat_members, private_chat_messages
import decorators
import utilities
from constants import BotSettingKey, Group, Regex, REGIONS_DATA, RegionName, MediaType, MONTHS_IT, TempDataKey, Timeout
from config import config

logger = logging.getLogger(__name__)


class EventFilter:
    # region
    IT = "it"
    NOT_IT = "notit"

    # type
    LEGAL = "legal"
    FREE = "free"
    NOT_FREE = "notfree"

    # time
    WEEK = "week"
    WEEK_2 = "week2"
    MONTH_AND_NEXT_MONTH = "monthnext"
    ALL = "all"
    SOON = "soon"


FILTER_DESCRIPTION = {
    EventFilter.IT: f"{Flag.ITALY} in italia",
    EventFilter.NOT_IT: f"{Emoji.EARTH} all'estero",
    EventFilter.FREE: f"{Emoji.PIRATE} freeparty",
    EventFilter.NOT_FREE: f"{Flag.BLACK} eventi legali, cs, squat, street parade, altro",
    EventFilter.WEEK: f"{Emoji.CALENDAR} questa settimana (da lunedì a domenica)",
    EventFilter.WEEK_2: f"{Emoji.CALENDAR} questa settimana (lun-dom) o la prossima",
    EventFilter.MONTH_AND_NEXT_MONTH: f"{Emoji.CALENDAR} questo mese o il prossimo",
    EventFilter.SOON: f"{Emoji.CLOCK} senza una data precisa (#soon)"
}


DEFAULT_FILTERS = [EventFilter.IT, EventFilter.NOT_FREE, EventFilter.WEEK]


def time_to_split(text_lines: List[str], entities_per_line: int) -> bool:
    message_length = len("\n\naggiornato al xx/xx/xxxx xx:xx")
    for line in text_lines:
        message_length += len(line)

    if message_length >= MessageLimit.MAX_TEXT_LENGTH:
        return True

    if len(text_lines) * entities_per_line >= MessageLimit.MESSAGE_ENTITIES:
        return True


def format_event_string(event: Event, message_date_instead_of_event_date=False) -> str:
    region_icon = ""
    if event.region and event.region in REGIONS_DATA:
        region_icon = REGIONS_DATA[event.region]["emoji"]

    if event.event_title:
        title_escaped = utilities.escape_html(event.event_title)
    else:
        title_escaped = "unnamed party"

    if event.canceled:
        title_escaped = f"<s>{title_escaped}</s>"

    if message_date_instead_of_event_date:
        date = utilities.format_datetime(event.message_date, format_str="msg date: %d/%m/%Y")
    else:
        date = event.pretty_date()

    # text = f"{event.icon()}{region_icon} <b>{title_escaped}</b> ({event.pretty_date()}) • <a href=\"{event.message_link()}\">fly & info</a>"
    text = f"{event.icon()}{region_icon} <b><a href=\"{event.message_link()}\">{title_escaped}</a></b> • {date}"

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


def extract_query_filters(args: List[str], today: Optional[datetime.date] = None) -> List:
    query_filters = []
    args = [arg.lower() for arg in args]

    # EVENT TYPE
    if EventFilter.NOT_FREE in args or EventFilter.LEGAL in args:
        # legal = anything that is not a free party
        query_filters.append(Event.event_type != EventType.FREE)
    elif EventFilter.FREE in args:
        query_filters.append(Event.event_type == EventType.FREE)

    # EVENT DATE
    today = today or datetime.date.today()
    if EventFilter.WEEK in args:
        last_monday = utilities.previous_weekday(today=today, weekday=0)
        next_monday = utilities.next_weekday(today=today, weekday=0)
        logger.debug(f"week filter: {last_monday} <= start date < {next_monday}")

        query_filters.extend([Event.start_date >= last_monday, Event.start_date < next_monday])
    elif EventFilter.WEEK_2 in args:
        last_monday = utilities.previous_weekday(today=today, weekday=0)
        next_monday = utilities.next_weekday(today=today, weekday=0, additional_days=7)
        logger.debug(f"week filter: {last_monday} <= start date < {next_monday}")

        query_filters.extend([Event.start_date >= last_monday, Event.start_date < next_monday])
    elif EventFilter.ALL in args:
        # all events >= this month
        query_filters.extend([
            Event.start_year >= today.year,
            Event.start_month >= today.month,
        ])
    elif EventFilter.SOON in args:
        query_filters.extend([Event.soon == true()])
    else:
        # no other time filter: this month + next month
        this_month = today.month
        next_month = today.month + 1 if today.month != 12 else 1

        query_filters.extend([
            Event.start_year >= today.year,
            Event.start_month.in_([this_month, next_month]),
        ])

    # EVENT REGION
    it_regions = [RegionName.ITALIA, RegionName.CENTRO_ITALIA, RegionName.NORD_ITALIA, RegionName.SUD_ITALIA]
    if EventFilter.IT in args:
        query_filters.append(Event.region.in_(it_regions))
    elif EventFilter.NOT_IT in args:
        query_filters.append(Event.region.not_in(it_regions))

    return query_filters


async def send_events_messages(message: Message, all_events_strings: List[str], protect_content: bool = True) -> List[Message]:
    sent_messages = []

    messages_to_send = split_messages(all_events_strings, return_after_first_message=False)

    if not messages_to_send:
        sent_message = await message.reply_text("vuoto :(", protect_content=protect_content)
        return [sent_message]

    total_messages = len(messages_to_send)
    for i, text_to_send in enumerate(messages_to_send):
        logger.debug(f"sending message {i + 1}/{total_messages}")
        # if i + 1 == total_messages:
        #     text_to_send += f"\n\nUsa /soon per gli eventi con data da programmare"

        sent_message = await message.reply_text(text_to_send, protect_content=protect_content)
        sent_messages.append(sent_message)

    return sent_messages


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/events {utilities.log(update)}")

    args = context.args if context.args else []
    all_events_strings = get_all_events_strings_from_db(session, args)

    # logger.debug(f"result: {len(messages_to_send)} messages, {len(text_lines)} lines")

    protect_content = not utilities.is_superadmin(update.effective_user)
    await send_events_messages(update.message, all_events_strings, protect_content)


def get_month_string(date_override: Optional[datetime.date]) -> str:
    now = date_override or utilities.now()
    this_month = now.month
    next_month = now.month + 1 if now.month != 12 else 1
    this_month_str = MONTHS_IT[this_month - 1][:3].lower()
    next_month_str = MONTHS_IT[next_month - 1][:3].lower()

    return f"{this_month_str} + {next_month_str}"


def get_events_reply_markup(args, date_override: Optional[datetime.date] = None) -> InlineKeyboardMarkup:
    keyboard = [[]]

    if EventFilter.NOT_IT in args:
        keyboard[0].append(InlineKeyboardButton(f"{Emoji.EARTH} estero", callback_data=f"changefilterto:{EventFilter.IT}"))
    else:
        keyboard[0].append(InlineKeyboardButton(f"{Flag.ITALY} italia", callback_data=f"changefilterto:{EventFilter.NOT_IT}"))

    if EventFilter.FREE in args:
        keyboard[0].append(InlineKeyboardButton(f"{Emoji.PIRATE} freeparty", callback_data=f"changefilterto:{EventFilter.NOT_FREE}"))
    else:
        keyboard[0].append(InlineKeyboardButton(f"{Flag.BLACK} altro", callback_data=f"changefilterto:{EventFilter.FREE}"))

    if EventFilter.WEEK in args:
        keyboard[0].append(InlineKeyboardButton(f"{Emoji.CALENDAR} settimana", callback_data=f"changefilterto:{EventFilter.WEEK_2}"))
    elif EventFilter.WEEK_2 in args:
        keyboard[0].append(InlineKeyboardButton(f"{Emoji.CALENDAR} 2 settimane", callback_data=f"changefilterto:{EventFilter.MONTH_AND_NEXT_MONTH}"))
    elif EventFilter.MONTH_AND_NEXT_MONTH in args:
        keyboard[0].append(InlineKeyboardButton(f"{Emoji.CALENDAR} {get_month_string(date_override)}", callback_data=f"changefilterto:{EventFilter.SOON}"))
    else:
        keyboard[0].append(InlineKeyboardButton(f"{Emoji.CLOCK} soon", callback_data=f"changefilterto:{EventFilter.WEEK}"))

    keyboard.append([InlineKeyboardButton(f"{Emoji.DONE} conferma", callback_data="eventsconfirm")])
    return InlineKeyboardMarkup(keyboard)


@decorators.catch_exception()
async def on_drop_events_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/dropeventscache {utilities.log(update)}")

    drop_events_cache(context)
    await update.message.reply_text("cache dropped")


def radar_save_date_override_to_user_data(context: ContextTypes.DEFAULT_TYPE):
    provided_date = context.args[0]

    strptime_formats_to_try = ["%Y%m%d", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"]
    today_object = None
    for strptime_format in strptime_formats_to_try:
        try:
            today_object = datetime.datetime.strptime(provided_date, strptime_format)
        except ValueError:
            continue

    if not today_object:
        logger.info(f"wrong date arg provided: {provided_date}")
        return

    today_object = today_object.date()
    logger.info(f"radar date override: {today_object}")
    context.user_data[TempDataKey.RADAR_DATE_OVERRIDE] = today_object
    return today_object


def can_use_radar(user_id: int):
    return user_id in config.settings.radar_enabled


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_ban()
async def on_radar_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/radar23 {utilities.log(update)}")

    if not chat_members.is_member(session, update.effective_user.id, Chat.is_users_chat) and not can_use_radar(update.effective_user.id):
        logger.info("user is not a member of the users chat and can't use the command")
        return

    command = utilities.get_command(update.message.text)
    if command.lower() == "radar24" and chat_members.is_member(session, update.effective_user.id, Chat.is_staff_chat):
        # only for staff chat members:
        logger.info("protect content override for staff chat member")
        context.user_data[TempDataKey.RADAR_PROTECT_CONTENT_OVERRIDE] = True

    # save to temp data the date the user passed, so we force-override todays' date when the confirm button is used
    date_override = None
    if context.args:
        date_override: Optional[datetime.date] = radar_save_date_override_to_user_data(context)

    # always try to get existing filters (they are not reset after the user confirms their query)
    args = context.user_data.get(TempDataKey.EVENTS_FILTERS, DEFAULT_FILTERS)
    logger.debug(f"existing filters: {args}")

    reply_markup = get_events_reply_markup(args, date_override)

    # override in case there was no existing filter
    context.user_data[TempDataKey.EVENTS_FILTERS] = args

    text = f"{Emoji.COMPASS} Usa i tasti qui sotto per cambiare i filtri della ricerca, poi usa conferma per vedere gli eventi"
    if date_override:
        text = f"{text} (data di riferimento: {date_override.strftime('%d/%m/%Y')})"

    setting: BotSetting = settings.get_or_create(session, BotSettingKey.RADAR_FILE)
    if setting.value():
        sent_message = await update.message.reply_animation(setting.value(), caption=text, reply_markup=reply_markup)
    else:
        sent_message = await update.message.reply_html(text, reply_markup=reply_markup)
    private_chat_messages.save(session, sent_message)


def safe_remove(items: List[str], item: str):
    try:
        items.remove(item)
    except ValueError:
        pass


@decorators.catch_exception(ignore_message_not_modified_exception=True)
@decorators.pass_session()
async def on_change_filter_cb(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"change filter callback query {utilities.log(update)}")

    args = context.user_data.get(TempDataKey.EVENTS_FILTERS, DEFAULT_FILTERS)
    new_filter = context.matches[0].group("filter")

    date_override: Optional[datetime.date] = None
    if new_filter == EventFilter.FREE:
        safe_remove(args, EventFilter.NOT_FREE)
        args.append(EventFilter.FREE)
    elif new_filter == EventFilter.NOT_FREE:
        safe_remove(args, EventFilter.FREE)
        args.append(EventFilter.NOT_FREE)
    elif new_filter == EventFilter.IT:
        safe_remove(args, EventFilter.NOT_IT)
        args.append(EventFilter.IT)
    elif new_filter == EventFilter.NOT_IT:
        safe_remove(args, EventFilter.IT)
        args.append(EventFilter.NOT_IT)
    elif new_filter == EventFilter.WEEK:
        safe_remove(args, EventFilter.WEEK_2)
        safe_remove(args, EventFilter.MONTH_AND_NEXT_MONTH)
        safe_remove(args, EventFilter.SOON)

        args.append(EventFilter.WEEK)
    elif new_filter == EventFilter.WEEK_2:
        safe_remove(args, EventFilter.WEEK)
        safe_remove(args, EventFilter.MONTH_AND_NEXT_MONTH)
        safe_remove(args, EventFilter.SOON)

        args.append(EventFilter.WEEK_2)
    elif new_filter == EventFilter.MONTH_AND_NEXT_MONTH:
        safe_remove(args, EventFilter.WEEK)
        safe_remove(args, EventFilter.WEEK_2)
        safe_remove(args, EventFilter.SOON)

        args.append(EventFilter.MONTH_AND_NEXT_MONTH)

        # we just need to get the date override here
        date_override = context.user_data.get(TempDataKey.RADAR_DATE_OVERRIDE, None)
    elif new_filter == EventFilter.SOON:
        safe_remove(args, EventFilter.WEEK)
        safe_remove(args, EventFilter.WEEK_2)
        safe_remove(args, EventFilter.MONTH_AND_NEXT_MONTH)

        args.append(EventFilter.SOON)

    logger.debug(f"new filters: {args}")

    context.user_data[TempDataKey.EVENTS_FILTERS] = args

    alert_text = FILTER_DESCRIPTION[new_filter]
    await update.callback_query.answer(alert_text)

    reply_markup = get_events_reply_markup(args, date_override)
    await update.callback_query.edit_message_reply_markup(reply_markup=reply_markup)


def args_key_in_cache(context: CallbackContext, args_cache_key: str) -> bool:
    if TempDataKey.EVENTS_CACHE not in context.bot_data:
        return False

    if args_cache_key not in context.bot_data[TempDataKey.EVENTS_CACHE]:
        return False

    now = utilities.now()
    time_delta = now - context.bot_data[TempDataKey.EVENTS_CACHE][args_cache_key][TempDataKey.EVENTS_CACHE_SAVED_ON]
    if time_delta.total_seconds() > Timeout.ONE_HOUR * 20:
        logger.info(f"cache expired for key {args_cache_key}")
        return False

    logger.info(f"cache hit for key {args_cache_key}")
    return True


def get_all_events_strings_from_cache(context: CallbackContext, args_cache_key: str) -> Optional[List]:
    """must be uased after checking whether the cache key is still cached, using args_key_in_cache()"""

    return context.bot_data[TempDataKey.EVENTS_CACHE][args_cache_key][TempDataKey.EVENTS_CACHE_DATA]


def get_all_events_strings_from_db(session: Session, args: List[str], date_override: Optional[datetime.date] = None) -> List[str]:
    query_filters = extract_query_filters(args, today=date_override)
    events_list: List[Event] = events.get_events(session, filters=query_filters)

    all_events_strings = []
    for i, event in enumerate(events_list):
        if not event.is_valid():
            logger.info(f"skipping invalid event: {event}")
            continue

        text_line = format_event_string(event)
        all_events_strings.append(text_line)

    return all_events_strings


def get_last_message_id_sent_for_cache_key(context: CallbackContext, args_cache_key: str) -> Optional[int]:
    if TempDataKey.EVENTS_CACHE not in context.user_data:
        return

    if args_cache_key not in context.user_data[TempDataKey.EVENTS_CACHE]:
        return

    # we do not need to check whether the cache is expired or not, because we enter the funciton only if
    # the same cache key is still valid in bot_data

    logger.debug(f"user cache hit for key {args_cache_key}")
    return context.user_data[TempDataKey.EVENTS_CACHE][args_cache_key]


def cache_message_id_for_cache_key(context: CallbackContext, args_cache_key: str, message_id: int):
    if TempDataKey.EVENTS_CACHE not in context.user_data:
        context.user_data[TempDataKey.EVENTS_CACHE] = {}

    context.user_data[TempDataKey.EVENTS_CACHE][args_cache_key] = message_id


def cache_all_events_strings_for_cache_key(context: CallbackContext, args_cache_key: str, all_events_strings: List[str]):
    if TempDataKey.EVENTS_CACHE not in context.bot_data:
        context.bot_data[TempDataKey.EVENTS_CACHE] = {}

    context.bot_data[TempDataKey.EVENTS_CACHE][args_cache_key] = {
        TempDataKey.EVENTS_CACHE_SAVED_ON: utilities.now(),
        TempDataKey.EVENTS_CACHE_DATA: all_events_strings,
    }


@decorators.catch_exception()
@decorators.pass_session()
async def on_events_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"confirm callback query {utilities.log(update)}")

    args = context.user_data.get(TempDataKey.EVENTS_FILTERS, DEFAULT_FILTERS)
    # we create a copy of the list because modifiyng `args`'s content
    # will also modify context.user_data[TempDataKey.EVENTS_FILTERS]
    args = args[:]

    # if the key exists (if it exists, it's always True), do *not* protect the content
    protect_content_override = context.user_data.pop(TempDataKey.RADAR_PROTECT_CONTENT_OVERRIDE, False)
    date_override: Optional[datetime.date] = context.user_data.pop(TempDataKey.RADAR_DATE_OVERRIDE, None)
    if date_override:
        # we cache the result *for this specific date override*, queries that
        # do not override the date should not be date-dependent
        logger.debug(f"date override detected: {date_override}")
        args.append(date_override.strftime("%Y%m%d"))

    args.sort()  # it's important to sort the args, see #82
    args_cache_key = "+".join(args)
    logger.debug(f"cache key: {args_cache_key}")

    if not args_key_in_cache(context, args_cache_key):
        all_events_strings = get_all_events_strings_from_db(session, args, date_override=date_override)

        logger.info(f"caching query result for key {args_cache_key}...")
        cache_all_events_strings_for_cache_key(context, args_cache_key, all_events_strings)
    else:  # cache key still valid in bot_data
        all_events_strings = get_all_events_strings_from_cache(context, args_cache_key)

        # only try this if the cache key exists in bot_data
        message_id: int = get_last_message_id_sent_for_cache_key(context, args_cache_key)
        logger.info(f"protect_content_override: {protect_content_override}")
        if message_id and not protect_content_override:
            # we do not reply to an old message if protect_content_override: this flag is set when an user uses /radar24,
            # which is supposed to send the un-content-protected list of events. It is pointless to reply to
            # an old message in this case

            logger.info(f"cache hit for key {args_cache_key} in user_data, replying to previously-sent list...")
            await update.effective_message.delete()  # delete the message as we will send the new ones
            await update.effective_message.reply_html(
                "^consulta questa lista, gli eventi non sono cambiati da quando è stata inviata",
                reply_to_message_id=message_id,
                quote=True
            )
            return

    # logger.debug(f"result: {len(messages_to_send)} messages, {len(text_lines)} lines")

    # do not pop existing filters, we will remember them for the next time the user uses /radar
    # context.user_data.pop(TempDataKey.EVENTS_FILTERS, None)

    await update.effective_message.delete()  # delete the message as we will send the new ones

    # protect_content = not utilities.is_superadmin(update.effective_user)
    protect_content = not protect_content_override
    sent_messages = await send_events_messages(update.effective_message, all_events_strings, protect_content)
    private_chat_messages.save(session, sent_messages)

    # just save the message_id of the first message sent
    logger.debug(f"caching user's message_id for key {args_cache_key}...")
    cache_message_id_for_cache_key(context, args_cache_key, sent_messages[0].message_id)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_ban()
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

        text_line = format_event_string(event, message_date_instead_of_event_date=True)
        all_events_strings.append(text_line)

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
@decorators.staff_admin()
async def on_delete_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/delevent {utilities.log(update)}")

    event: Event = await event_from_link(update, context, session)
    if not event:
        # event_from_link() will also answer the user
        return

    # session.delete(event)
    event.deleted = True

    event_str = format_event_string(event)
    await update.effective_message.reply_text(f"{event_str}\n\n^event deleted")

    drop_events_cache(context)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.staff_admin()
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


HANDLERS = (
    (CommandHandler(["radar", "radar23", "radar24"], on_radar_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CallbackQueryHandler(on_change_filter_cb, pattern=r"changefilterto:(?P<filter>\w+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_events_confirm_cb, pattern=r"eventsconfirm$"), Group.NORMAL),
    (CommandHandler(["invalidevents", "ie"], on_invalid_events_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["delevent", "de"], on_delete_event_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["getpost"], on_getpost_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    # superadmins
    (CommandHandler(["events"], on_events_command, filters=Filter.SUPERADMIN), Group.NORMAL),
    (CommandHandler(["dropeventscache", "dec"], on_drop_events_cache_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["parseevents", "pe"], on_parse_events_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
