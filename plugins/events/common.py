import datetime
import logging
import re
from re import Match
from typing import Optional, List, Union

from telegram import Message, MessageEntity
from telegram.ext import filters, CallbackContext

from config import config
from database.models import Event, EVENT_TYPE
import utilities
from constants import Regex, REGIONS_DATA, TempDataKey

logger = logging.getLogger(__name__)


class EventDate:
    SEP = "/"

    def __init__(self, year: int, month: int, day: Optional[Union[int, str]] = None):
        self.month: int = month
        self.year: int = year

        if (isinstance(day, str) and ("?" in day or "x" in day.lower())) or day is None:
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

    def to_date(self) -> datetime.date:
        if not self.day:
            raise ValueError("cannot return a date if day is missing")

        return datetime.date(year=self.year, month=self.month, day=self.day)


class DateMatchNormal:
    NAME = "DateMatchNormal"
    # https://regex101.com/r/MnrWDz/6
    PATTERN = (
        r"(?P<start_day>\d{1,2}|[\?x]+)(?:-(?P<end_day>\d{1,2}|[\?x]+))?[/.](?P<month>\d{1,2})(?:[/.](?P<year>(?:20)?2\d))",
    )

    @staticmethod
    def extract(match: Match):
        start_day_str = match.group("start_day").lower()
        if "?" in start_day_str or "x" in start_day_str:
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
            if "?" in end_day_str or "x" in end_day_str.lower():
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
        # "." inside a "[]" matches the character "." literally
        r"(?P<days>(?:\d{1,2}[.-]?)+)/(?P<month>\d{1,2})/(?P<year>(?:20)?2[3-9])(?![.-])",  # https://regex101.com/r/f9vJkw
        r"(?P<days>(?:\d{1,2}[/-]?)+)\.(?P<month>\d{1,2})\.(?P<year>(?:20)?2[3-9])(?![/-])",  # https://regex101.com/r/QkzVSg
        r"(?P<days>(?:\d{1,2}[/.]?)+)-(?P<month>\d{1,2})-(?P<year>(?:20)?2[3-9])(?![/.])",  # https://regex101.com/r/wKMaKI
        r"(?P<days>(?:\d{1,2}[/.-]?)+)[/.-](?P<month>\d{1,2})[/.-](?P<year>(?:20)?2[3-9])",  # https://regex101.com/r/OFIsou
    )

    @staticmethod
    def extract(match: Match):
        days_str = match.group("days")
        days_list = []
        separators = (".", "-", "/")
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


def add_event_message_metadata(message: Message, event: Event, reparse: bool = False):
    message_text = message.text or message.caption

    event.message_text = message_text

    if not reparse:
        # do not override these properties if the message text is being re-parsed on request
        event.message_date = message.date
        event.message_edit_date = message.edit_date
        event.message_json = message.to_json()

        event.media_group_id = message.media_group_id

    if utilities.contains_media_with_file_id(message):
        # we do not remove the media metadata if the utility function returns false: a media message
        # cannot be edited and turned into a text message
        # this means that if we ask to /reparse a media channel post by just providing the text, the media
        # metadata should not (and won't) be erased
        event.media_file_id, event.media_file_unique_id, event.media_group_id = utilities.get_media_ids(message)
        event.media_type = utilities.detect_media_type(message)


MONTHS = (
    "#gennaio",
    "#febbraio",
    "#marzo",
    "#aprile",
    "#maggio",
    "#giugno",
    "#luglio",
    "#agosto",
    "#settembre",
    "#ottobre",
    "#novembre",
    "#dicembre"
)


def parse_message_entities_list(hashtags_list: List[str], event: Event):
    event.save_hashtags(hashtags_list)

    # TYPE
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

    # SOON
    if "#soon" in hashtags_list or "#comingsoon" in hashtags_list:
        event.soon = True
    else:
        # un-soon events that do not have these hashtags
        event.soon = False

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

    # DATES
    # enter this only if dates are not already filled
    # they will be overwritten when the text is parsed
    if not event.start_month and not event.start_year:
        for i, month_hashtag in enumerate(MONTHS):
            if month_hashtag not in hashtags_list:
                continue

            month = i + 1
            year = utilities.now().year
            if month < utilities.now().month:
                year += 1

            event.start_month = month
            event.start_year = year

            event.end_month = month
            event.end_year = year


def parse_message_entities(message: Message, event: Event):
    # HASHTAGS
    hashtags_dict = message.parse_entities([MessageEntity.HASHTAG]) if message.text else message.parse_caption_entities([MessageEntity.HASHTAG])
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
        if start_date.day:
            event.start_date = start_date.to_date()


def drop_events_cache(context: CallbackContext):
    if TempDataKey.EVENTS_CACHE in context.bot_data:
        context.bot_data.pop(TempDataKey.EVENTS_CACHE)
        return True

    return False

