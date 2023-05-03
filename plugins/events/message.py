import datetime
import logging
import re
from re import Match
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session
from telegram import Update, Message, MessageEntity
from telegram.ext import ContextTypes, filters, MessageHandler, CommandHandler

from database.base import session_scope
from database.models import Chat, Event, EventTypeHashtag, EVENT_TYPE, User, BotSetting
from database.queries import settings, events
import decorators
import utilities
from constants import BotSettingKey, Group, Regex, REGIONS_DATA
from config import config

logger = logging.getLogger(__name__)

with session_scope() as session:
    setting: BotSetting = settings.get_or_create(session, BotSettingKey.EVENTS_CHAT_ID)
    if not setting.value():
        logger.debug(f"setting events chat id: {config.events.chat_id}")
        setting.update_value(config.events.chat_id)
        session.commit()

    chat_id_filter = filters.Chat(setting.value())

update_type_filter = filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE | filters.UpdateType.CHANNEL_POST | filters.UpdateType.EDITED_CHANNEL_POST

message_type_filter = filters.TEXT | filters.CAPTION


def check_day(day: int, month: int, year: int):
    if month in (1, 3, 5, 7, 8, 10, 12) and not (1 <= day <= 31):
        raise ValueError("provided day must be in 1..31")
    if month in (4, 6, 9, 11) and not (1 <= day <= 30):
        raise ValueError("provided day must be in 1..30")
    if month == 2:
        if utilities.is_leap_year(year) and not (1 <= day <= 29):
            raise ValueError("provided day must be in 1..29")
        elif not utilities.is_leap_year(year) and not (1 <= day <= 28):
            raise ValueError("provided day must be in 1..28")


def check_month(month: int):
    if not (1 <= month <= 12):
        raise ValueError("provided month must be in 1..12")


def format_year(year: Optional[str] = None) -> int:
    if year:
        if len(year) == 2:
            year = f"20{year}"
    else:
        year = datetime.datetime.now().year

    year = int(year)

    return year


class EventDate:
    SEP = "/"

    def __init__(self, year: int, month: int, day: Optional[int] = None):
        self.day: int = day
        self.month: int = month
        self.year: int = year

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
        check_month(self.month)
        if self.day:
            check_day(self.day, self.month, self.year)

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
        year: int = format_year(year)

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
        year: int = format_year(year)

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


def parse_event(message: Message, event: Event):
    message_text = message.text or message.caption

    if not message_text:
        logger.info("message does not contain any text")
        return

    # HASHTAGS
    hashtags_dict = message.parse_entities(MessageEntity.HASHTAG) if message.text else message.parse_caption_entities(MessageEntity.HASHTAG)
    hashtags_list = [v.lower() for v in hashtags_dict.values()]
    event.save_hashtags(hashtags_list)
    for hashtag, event_type in EVENT_TYPE.items():
        if hashtag in hashtags_list:
            event.event_type = event_type

    # CANCELED
    if "#annullata" in hashtags_list or "#annullato" in hashtags_list:
        event.canceled = True

    # REGION
    for region_name, region_data in REGIONS_DATA.items():
        for region_hashtag in region_data["hashtags"]:
            if region_hashtag in hashtags_list:
                event.region = region_name
                # return after the first match
                break

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
    add_event_message_metadata(update.effective_message, event)
    parse_event(update.effective_message, event)

    logger.info(f"parsed event: {event}")

    session.commit()


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_set_events_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"/seteventschat {utilities.log(update)}")

    events_chat_setting: BotSetting = settings.get_or_create(session, BotSettingKey.EVENTS_CHAT_ID)

    chat_id_filter.chat_ids = {update.effective_chat.id}

    events_chat_setting.update_value(update.effective_chat.id)

    await update.effective_message.reply_text(f"this chat has been set as the events chat (<code>{update.effective_chat.id}</code>)")


HANDLERS = (
    (MessageHandler(chat_id_filter & update_type_filter & message_type_filter, on_event_message), Group.PREPROCESS),
    (CommandHandler("seteventschat", on_set_events_chat_command, filters=filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST), Group.NORMAL),
)
