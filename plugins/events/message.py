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

from database.base import session_scope
from database.models import Chat, Event, EventTypeHashtag, EVENT_TYPE, User, BotSetting
from database.queries import settings, events
import decorators
import utilities
from constants import BotSettingKey, Group, Regex, REGIONS_DATA
from config import config

logger = logging.getLogger(__name__)

with session_scope() as tmp_session:
    setting: BotSetting = settings.get_or_create(tmp_session, BotSettingKey.EVENTS_CHAT_ID)
    if not setting.value():
        logger.debug(f"setting events chat id: {config.events.chat_id}")
        setting.update_value(config.events.chat_id)
        tmp_session.commit()

    chat_id_filter = filters.Chat(setting.value())


class Filter:
    UPDATE_TYPE = filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE | filters.UpdateType.CHANNEL_POST | filters.UpdateType.EDITED_CHANNEL_POST
    UPDATE_TYPE_NEW_MESSAGE = filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST
    MESSAGE_TYPE = filters.TEXT | filters.CAPTION
    ADMIN_PRIVATE = filters.ChatType.PRIVATE & filters.User(config.telegram.admins)


class EventDate:
    SEP = "/"

    def __init__(self, year: int, month: int, day: Optional[Union[int, str]] = None):
        self.month: int = month
        self.year: int = year

        if (isinstance(day, str) and "?" in day) or day is None:
            self.day = None
        else:
            self.day = int(day)

    @property
    def day_str(self):
        return f"{self.day:02}" if self.day else '??'

    @property
    def month_str(self):
        return f"{self.month:02}" if self.month else '??'

    @property
    def year_str(self):
        return str(self.year)

    def is_valid(self):
        return self.month and self.year

    def validate(self):
        utilities.check_month(self.month)
        if self.day:
            utilities.check_day(self.day, self.month, self.year)

    def fix_months_overlap(self, start_day: Optional[int] = None) -> bool:
        # convenience method needed if the parsed date string overlaps two months
        # for example: 30-02/05/2023

        # start_day migth be None
        if start_day and self.day < start_day:
            self.month += 1
            return True

        return False

    def __str__(self):
        return f"{self.day_str}{self.SEP}{self.month_str}{self.SEP}{self.year}"

    def to_str(self):
        return str(self)


class DateMatchNormal:
    NAME = "DateMatchNormal"
    # https://regex101.com/r/MnrWDz/6
    PATTERN = (
        r"(?P<start_day>\d{1,2}|\?+)(?:-(?P<end_day>\d{1,2}|\?+))?[/.](?P<month>\d{1,2})(?:[/.](?P<year>\d{2,4}))?",
    )

    @staticmethod
    def extract(match: Match):
        start_day_str = match.group("start_day")
        if "?" in start_day_str:
            start_day = None
        else:
            start_day = int(start_day_str)

        month = int(match.group("month"))
        year: str = match.group("year")
        year: int = utilities.format_year(year)

        start_date = EventDate(year, month, start_day)
        start_date.validate()

        end_day_str = match.group("end_day")
        if not end_day_str:
            end_date = EventDate(year, month, start_day)
        else:
            if "?" in end_day_str:
                end_date = EventDate(year, month)
            else:
                end_day = int(end_day_str)

                end_date = EventDate(year, month, end_day)
                end_date.fix_months_overlap(start_date.day)

            end_date.validate()

        logger.debug(f"parsed dates: {start_date}; {end_date}")
        return start_date, end_date


class DateMatchDaysList:
    NAME = "DateMatchDaysList"
    PATTERN = (
        r"(?P<days>(?:\d{1,2}[\.-]?)+)/(?P<month>\d{1,2})/(?P<year>\d{2,4})(?![\.-])",  # https://regex101.com/r/f9vJkw/6
        r"(?P<days>(?:\d{1,2}[/-]?)+)\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})(?![/-])",  # https://regex101.com/r/QkzVSg/3
        r"(?P<days>(?:\d{1,2}[/\.]?)+)-(?P<month>\d{1,2})-(?P<year>\d{2,4})(?![/\.])",  # https://regex101.com/r/wKMaKI/3
    )

    @staticmethod
    def extract(match: Match):
        days_str = match.group("days")
        days_list = []
        separators = (".", "-")
        for sep in separators:
            if sep in days_str:
                days_list = days_str.split(sep)
                break

        if not days_list:
            raise ValueError(f"string \"{days_str}\" couldn't be split by any of {separators}")

        month = int(match.group("month"))
        year: str = match.group("year")
        year: int = utilities.format_year(year)

        start_date = EventDate(year, month, int(days_list[0]))
        start_date.validate()

        end_date = EventDate(year, month, int(days_list[-1]))
        end_date.fix_months_overlap(start_date.day)
        end_date.validate()

        logger.debug(f"parsed dates: {start_date}; {end_date}")
        return start_date, end_date


def add_event_message_metadata(message: Message, event: Event):
    message_text = message.text or message.caption

    event.message_date = message.date
    event.message_edit_date = message.edit_date
    event.message_text = message_text
    event.message_json = message.to_json()

    event.media_group_id = message.media_group_id
    if message.effective_attachment and (isinstance(message.effective_attachment, tuple) or message.effective_attachment.file_unique_id):
        if isinstance(message.effective_attachment, tuple):
            event.media_file_id = message.effective_attachment[-1].file_id
            event.media_file_unique_id = message.effective_attachment[-1].file_unique_id
        else:
            event.media_file_id = message.effective_attachment.file_id
            event.media_file_unique_id = message.effective_attachment.file_unique_id


def parse_message_entities_list(hashtags_list: List[str], event: Event):
    event.save_hashtags(hashtags_list)
    for hashtag, event_type in EVENT_TYPE.items():
        if hashtag in hashtags_list:
            event.event_type = event_type
            break

    # CANCELED
    if "#annullata" in hashtags_list or "#annullato" in hashtags_list:
        event.canceled = True
    else:
        # un-cancel events that do not have these hashtags
        event.canceled = False

    # REGION
    region_found = False
    for region_name, region_data in REGIONS_DATA.items():
        for region_hashtag in region_data["hashtags"]:
            if region_hashtag.lower() in hashtags_list:
                # logger.debug(f"found {region_hashtag}")
                event.region = region_name
                # return after the first match
                region_found = True
                break

        if region_found:
            break


def parse_message_entities(message: Message, event: Event):
    # HASHTAGS
    hashtags_dict = message.parse_entities(MessageEntity.HASHTAG) if message.text else message.parse_caption_entities(MessageEntity.HASHTAG)
    hashtags_list = [v.lower() for v in hashtags_dict.values()]
    parse_message_entities_list(hashtags_list, event)


def parse_message_entities_dict(message_dict: dict, event: Event):
    text = None
    if "text" in message_dict and message_dict["text"]:
        text = message_dict["text"]
    if "caption" in message_dict and message_dict["caption"]:
        text = message_dict["caption"]

    entities = None
    if "entities" in message_dict and message_dict["entities"]:
        entities = message_dict["entities"]
    if "caption_entities" in message_dict and message_dict["caption_entities"]:
        entities = message_dict["caption_entities"]

    if not text or not entities:
        return

    hashtags_list = []
    for entity in entities:
        if entity["type"] != MessageEntity.HASHTAG:
            continue

        hashtag = utilities.extract_entity(text, entity["offset"], entity["length"])
        hashtags_list.append(hashtag.lower())

    parse_message_entities_list(hashtags_list, event)


def parse_message_text(message_text: str, event: Event):
    # TITLE
    title_match = re.search(Regex.FIRST_LINE, message_text, re.M)
    if title_match:
        event.event_title = title_match.group(1)
    else:
        logger.info("couldn't parse any title")

    # DATES
    parsing_success = False
    date_tests = [DateMatchDaysList, DateMatchNormal]
    for date_test in date_tests:
        date_match = None
        for pattern in date_test.PATTERN:
            date_match = re.search(pattern, message_text, re.M)
            if date_match:
                break

        if not date_match:
            continue

        logger.info(f"pattern match successfull: {date_test.NAME}")

        try:
            start_date, end_date = date_test.extract(date_match)
            parsing_success = True
            break
        except ValueError as e:
            logger.info(f"error while parsing date with test '{date_test.NAME}': {e}")

    if not parsing_success:
        logger.info("couldn't parse any date with any regex")
    else:
        event.start_day = start_date.day
        event.start_month = start_date.month
        event.start_year = start_date.year
        event.end_day = end_date.day
        event.end_month = end_date.month
        event.end_year = end_date.year


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_event_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"events chat message update in {utilities.log(update)}")
    chat_id = update.effective_chat.id
    message_id = update.effective_message.message_id

    event = events.get_or_create(session, chat_id, message_id)
    if event.deleted:
        logger.debug(f"event ({event.chat_id}; {event.message_id}) was deleted: skipping update")
        return

    add_event_message_metadata(update.effective_message, event)
    parse_message_entities(update.effective_message, event)
    parse_message_text(update.effective_message.text or update.effective_message.caption, event)

    logger.info(f"parsed event: {event}")

    session.commit()


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

    events_chat_id = update.message.reply_to_message.forward_from_chat.id
    events_chat_title = update.message.reply_to_message.forward_from_chat.title

    events_chat_setting: BotSetting = settings.get_or_create(session, BotSettingKey.EVENTS_CHAT_ID)

    chat_id_filter.chat_ids = {events_chat_id}

    events_chat_setting.update_value(events_chat_id)

    await update.effective_message.reply_text(f"{utilities.escape_html(events_chat_title)} chat has been set "
                                              f"as the events chat (<code>{events_chat_id}</code>)")


def time_to_split(text_lines: List[str], entities_per_line: int) -> bool:
    message_length = 0
    for line in text_lines:
        message_length += len(line)

    if message_length >= MessageLimit.MAX_TEXT_LENGTH:
        return True

    if len(text_lines) * entities_per_line >= MessageLimit.MESSAGE_ENTITIES:
        return True


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/events {utilities.log(update)}")

    events_list: List[Event] = events.get_events(session)
    messages_to_send = []
    text_lines = []
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

        text_line = f"{event.icon()}{region_icon} <b>{title_escaped}</b> ({event.pretty_date()}) • <a href=\"{event.message_link()}\">fly & info</a>"

        if time_to_split(text_lines, entities_per_line=2):
            new_message_to_send = "\n".join(text_lines)
            messages_to_send.append(new_message_to_send)
            text_lines = [text_line]
        else:
            text_lines.append(text_line)

    if text_lines:
        new_message_to_send = "\n".join(text_lines)
        messages_to_send.append(new_message_to_send)

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

        text_lines.append(f"{event.message_link()}")

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


HANDLERS = (
    (MessageHandler(chat_id_filter & Filter.UPDATE_TYPE & Filter.MESSAGE_TYPE, on_event_message), Group.PREPROCESS),
    (CommandHandler(["seteventschat", "sec"], on_set_events_chat_command, filters=Filter.ADMIN_PRIVATE), Group.NORMAL),
    (CommandHandler(["events"], on_events_command, filters=filters.User(config.telegram.admins)), Group.NORMAL),
    (CommandHandler(["invalidevents", "ie"], on_invalid_events_command, filters=Filter.ADMIN_PRIVATE), Group.NORMAL),
    (CommandHandler(["parseevents", "pe"], on_parse_events_command, filters=Filter.ADMIN_PRIVATE), Group.NORMAL),
    (CommandHandler(["delevent", "de"], on_delete_event_command, filters=Filter.ADMIN_PRIVATE), Group.NORMAL),
)
