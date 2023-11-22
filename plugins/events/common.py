import copy
import datetime
import logging
import re
from re import Match
from typing import Optional, List, Union, Tuple, Sequence, Dict

from sqlalchemy import true, null
from sqlalchemy.orm import Session
from telegram import Message, MessageEntity
from telegram.constants import MessageLimit
from telegram.ext import CallbackContext

import utilities
from constants import Regex, RegionName, REGIONS_DATA, TempDataKey, MONTHS_IT
from database.models import Event, EVENT_TYPE, EventType, EventTypeHashtag
from database.queries import events
from emojis import Emoji, Flag

logger = logging.getLogger(__name__)


MAX_EVENT_TITLE_LEN = 100


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
    # https://regex101.com/r/MnrWDz
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
        # eg. 25-26-27/11/2023, 11-12/11/2023, 24/25/26/27/28/11/2023
        r"(?P<days>(?:\d{1,2}[\.\-/]?)+)[/.\-](?P<month>\d{1,2})[/.\-](?P<year>(?:2[0k])?2[3-9])(?![\.-/])",  # https://regex101.com/r/OLJZJo
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
            raise ValueError(f"days list \"{days_str}\" couldn't be split by any of {separators}")

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


class DateMatchMonthsJump:
    NAME = "DateMatchMonthsJump"
    PATTERN = (
        # "." inside a "[]" matches the character "." literally
        r"\b(?P<start_day>[0-3]?[0-9])[/.](?P<start_month>[0-1]?[0-9])(?:[./](?P<start_year>(?:2[0K])?2[3-9]))? *(?:[-/]|[-–]>) *(?P<end_day>(?:[0-3]?[0-9]|\?\?|xx))[/.](?P<end_month>[0-1]?[0-9])(?:[/.](?P<end_year>(?:2[0K])?2[3-9]))",  # https://regex101.com/r/eacPKF
    )

    @staticmethod
    def extract(match: Match):
        # DAY
        # for this kind of dates format, we always expect a start day
        start_day_str = match.group("start_day").lower()
        start_day = int(start_day_str)

        end_day_str = match.group("end_day").lower()
        if "?" in end_day_str or "x" in end_day_str:
            end_day = None
        else:
            end_day = int(end_day_str)

        # MONTH
        start_month = int(match.group("start_month"))
        end_month = int(match.group("end_month"))

        # YEAR
        end_year: str = match.group("end_year")
        end_year: int = utilities.format_year(end_year)

        start_year: str = match.group("start_year")
        if start_year:
            start_year: int = utilities.format_year(start_year)
        else:
            start_year: int = copy.deepcopy(end_year)
            if start_month == 12 and end_month == 1:
                start_year -= 1

        # VALIDATE
        start_date = EventDate(start_year, start_month, start_day)
        start_date.validate()

        end_date = EventDate(end_year, end_month, end_day)
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

    # LOCALATA
    if EventTypeHashtag.LOCALATA in hashtags_list:
        event.localata = True
    else:
        event.localata = False

    # CANCELED
    if (
        "#annullata" in hashtags_list
        or "#annullato" in hashtags_list
        or "#canceled" in hashtags_list
        or "#cancelled" in hashtags_list
        or "#rimandata" in hashtags_list
        or "#rimandato" in hashtags_list
        or "#posticipato" in hashtags_list
        or "#posticipata" in hashtags_list
    ):
        event.canceled = True
    else:
        # un-cancel events that do not have these hashtags
        event.canceled = False

    # SOON
    if "#soon" in hashtags_list or "#comingsoon" in hashtags_list or "#moreinfosoon" in hashtags_list:
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
    if not region_found:
        # if no region is found in the hashtags list, set it to NULL
        event.region = None

    # DATES
    # enter this only if dates are not already filled
    if not event.start_month and not event.start_year:
        month_hashtag_found = False
        for i, month_hashtag in enumerate(MONTHS):
            if month_hashtag not in hashtags_list:
                continue

            month_hashtag_found = True

            month = i + 1
            year = utilities.now().year
            if month < utilities.now().month:
                year += 1

            event.start_month = month
            event.start_year = year

            event.end_month = month
            event.end_year = year

            event.dates_from_hashtags = True

        if not month_hashtag_found:
            # set to false if no month hashtag was found
            event.dates_from_hashtags = False


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
    date_tests = [DateMatchMonthsJump, DateMatchDaysList, DateMatchNormal]
    for date_test in date_tests:
        date_match = None
        for i, pattern in enumerate(date_test.PATTERN):
            logger.debug(f"testing pattern #{i} for regex '{date_test.NAME}'")
            date_match = re.search(pattern, message_text, re.M | re.I)
            if date_match:
                logger.debug("pattern match successfull")
                break

        if not date_match:
            continue

        try:
            start_date, end_date = date_test.extract(date_match)
            parsing_success = True
            break
        except ValueError as e:
            logger.info(f"error while extracting date with test '{date_test.NAME}': {e}")
            continue

    if not parsing_success:
        logger.info("couldn't parse any date with any regex")
        event.reset_date_fields()
    else:
        event.start_day = start_date.day
        event.start_month = start_date.month
        event.start_year = start_date.year
        event.end_day = end_date.day
        event.end_month = end_date.month
        event.end_year = end_date.year

        event.populate_date_fields()
        event.dates_from_hashtags = False


def drop_events_cache(context: CallbackContext):
    if TempDataKey.EVENTS_CACHE in context.bot_data:
        context.bot_data.pop(TempDataKey.EVENTS_CACHE)
        return True

    return False


class EventFormatting:
    def __init__(self, bold=True, region_emoji=True, discussion_group_link=True, use_message_date=False):
        self.bold = bold
        self.region_emoji = region_emoji
        self.discussion_group_link = discussion_group_link
        self.use_message_date = use_message_date

    def __str__(self):
        defaults = EventFormatting()  # mention only non-default properties
        options = []
        if self.bold != defaults.bold:
            options.append(f"bold={self.bold}")
        if self.region_emoji != defaults.region_emoji:
            options.append(f"region_emoji={self.region_emoji}")
        if self.discussion_group_link != defaults.discussion_group_link:
            options.append(f"discussion_group_link={self.discussion_group_link}")
        if self.use_message_date != defaults.use_message_date:
            options.append(f"use_message_date={self.use_message_date}")

        options_str = ", ".join(options)
        return f"EventFormatting({options_str})"


def format_event_string(event: Event, formatting: Optional[EventFormatting] = None) -> Tuple[str, int]:
    if not formatting:
        formatting = EventFormatting()

    region_icon = ""
    if event.region and event.region in REGIONS_DATA:
        region_icon = REGIONS_DATA[event.region]["emoji"]

    if event.event_title:
        if len(event.event_title) > MAX_EVENT_TITLE_LEN:
            title = event.event_title[:MAX_EVENT_TITLE_LEN] + "..."
        else:
            title = event.event_title

        # https://stackoverflow.com/q/12410242
        title_escaped = utilities.escape_html(title.title())
    else:
        title_escaped = "unnamed party"

    if event.canceled:
        title_escaped = f"<s>{title_escaped}</s>"

    if formatting.use_message_date:
        date = utilities.format_datetime(event.message_date, format_str="msg date: %d/%m/%Y")
    else:
        date = event.pretty_date(week_number=False)

    # text = f"{event.icon()}{region_icon} <b>{title_escaped}</b> ({event.pretty_date()}) • <a href=\"{event.message_link()}\">fly & info</a>"
    title_with_link = f"<b><a href=\"{event.message_link()}\">{title_escaped}</a></b>"
    if formatting.discussion_group_link and event.discussion_group_message_id:
        # add a link to the post in the discussion group
        title_with_link = f"{title_with_link} [<a href=\"{event.discussion_group_message_link()}\">➜{Emoji.PEOPLE}</a>]"

    text = f"{event.icon()}{region_icon} {title_with_link} • {date}"

    return text, utilities.count_html_entities(text)


def time_to_split(
        text_lines: List[str],
        initial_message_length: int = 0,
        initial_entities_count: int = 0
) -> bool:
    # message_length = len("\n\naggiornato al xx/xx/xxxx xx:xx")

    # we do this thing to avoid to create references
    message_length = 0
    message_length += initial_message_length
    entities_count = 0
    entities_count += initial_entities_count

    for line in text_lines:
        message_length += len(line)
        entities_count += utilities.count_html_entities(line)

    if message_length >= MessageLimit.MAX_TEXT_LENGTH:
        return True

    if entities_count >= MessageLimit.MESSAGE_ENTITIES:
        return True


def split_messages(all_events: List[str], return_after_first_message=False) -> List[str]:
    messages_to_send = []
    next_message_events = []
    for events_string in all_events:
        if time_to_split(next_message_events):
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


class EventFilter:
    # region
    IT = "i"
    NOT_IT = "ni"

    # type
    LEGAL = "l"
    FREE = "f"
    NOT_FREE = "nf"

    # time
    WEEK = "w"
    WEEK_2 = "w2"
    MONTH_AND_NEXT_MONTH = "mn"
    MONTH_FUTURE_AND_NEXT_MONTH = "mfn"
    SOON = "s"
    ALL = "a"
    FUTURE_AND_UNKNOWN_THIS_MONTH = "futm"


FILTER_DESCRIPTION = {
    # region
    EventFilter.IT: f"{Flag.ITALY} in italia",
    EventFilter.NOT_IT: f"{Emoji.EARTH} all'estero",

    # type
    EventFilter.LEGAL: f"{Emoji.TICKET} eventi legali",
    EventFilter.FREE: f"{Emoji.PIRATE} freeparty",
    EventFilter.NOT_FREE: f"{Flag.BLACK} eventi legali, cs, squat, street parade, altro",

    # time
    EventFilter.WEEK: f"{Emoji.CALENDAR} questa settimana (da lunedì a domenica)",
    EventFilter.WEEK_2: f"{Emoji.CALENDAR} questa settimana (lun-dom) o la prossima",
    EventFilter.MONTH_AND_NEXT_MONTH: f"{Emoji.CALENDAR} questo mese (tutte) o il prossimo",
    EventFilter.MONTH_FUTURE_AND_NEXT_MONTH: f"{Emoji.CALENDAR} questo mese o il prossimo",
    EventFilter.SOON: f"{Emoji.CLOCK} senza una data precisa (#soon)",
    EventFilter.ALL: f"{Emoji.CLOCK} questo mese + futuri"
}


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
    if EventFilter.WEEK in args or EventFilter.WEEK_2 in args:
        additional_days = 0
        if EventFilter.WEEK_2 in args:
            # events of this week + events of the next week
            additional_days = 7

        last_monday = utilities.previous_weekday(today=today, weekday=0)
        next_monday = utilities.next_weekday(today=today, weekday=0, additional_days=additional_days)

        logger.debug(f"week filter: {last_monday} <= start/end date < {next_monday}")

        query_filters.extend([
            # start date is between last monday and next monday...
            (
                (Event.start_date >= last_monday)
                & (Event.start_date < next_monday)
            )
            # ...or end date exists and is between last monday and next monday (extract also
            # events which end during the week/weeks)
            | (
                Event.end_date.is_not(null())
                & (Event.end_date >= last_monday)
                & (Event.end_date < next_monday)
            )
        ])
    elif EventFilter.SOON in args:
        query_filters.extend([Event.soon == true()])
    elif EventFilter.MONTH_FUTURE_AND_NEXT_MONTH in args:
        this_day = today.day
        this_month = today.month
        this_month_year = today.year
        prev_month = today.month - 1 if today.month != 1 else 12
        prev_month_year = today.year if prev_month != 1 else today.year - 1
        next_month = today.month + 1 if today.month != 12 else 1
        next_month_year = today.year if this_month != 12 else today.year + 1
        # logger.info(f"this month: {this_month}/{this_month_year}; next month: {next_month}/{next_month_year}")

        # we need this date to extract all events that do not have an end date, but
        # that started recently in the past. The party might last several days, so we
        # decide to extract all events started within n days ago
        no_end_tolerance_date = today + datetime.timedelta(days=-7)

        query_filters.extend([
            # all events that start next month
            ((Event.start_month == next_month) & (Event.start_year == next_month_year))
            | (
                # all events starting this month...
                (Event.start_month == this_month) & (Event.start_year == this_month_year)
                & (
                    (Event.start_day.is_(null()))  # ...and they don't have a start date
                    | (this_day <= Event.start_day)  # ...or they start today/in the future
                    | (this_day <= Event.end_day)  # ...or they end today/in the future
                 )
            )
            | (
                # events that do not have an end day, but
                # their start date is between `no_end_tolerance_date` and today
                (Event.end_day.is_(null())) & (Event.start_day.is_not(null()))
                & (Event.start_date >= no_end_tolerance_date)
                & (Event.start_date <= today)
            )
        ])
    elif EventFilter.MONTH_AND_NEXT_MONTH in args:
        # no other time filter: this month + next month
        this_month = today.month
        next_month = today.month + 1 if today.month != 12 else 1

        query_filters.extend([
            Event.start_year >= today.year,
            Event.start_month.in_([this_month, next_month]),
        ])
    else:  # default: EventFilter.ALL
        # all events >= this month
        query_filters.extend([
            Event.start_year >= today.year,
            Event.start_month >= today.month,
        ])

    # EVENT REGION
    it_regions = [RegionName.ITALIA, RegionName.CENTRO_ITALIA, RegionName.NORD_ITALIA, RegionName.SUD_ITALIA, RegionName.SICILIA, RegionName.SARDEGNA]
    if EventFilter.IT in args:
        query_filters.append(Event.region.in_(it_regions))
    elif EventFilter.NOT_IT in args:
        query_filters.append(Event.region.not_in(it_regions))

    return query_filters


class OrderBy:
    DATE = "obd"
    WEEK_NUMBER = "obw"
    TITLE = "obet"
    TYPE = "obt"
    REGION = "obr"


ORDER_BY_DESCRIPTION = {
    OrderBy.DATE: "per data inizio",
    OrderBy.WEEK_NUMBER: "per settimana inizio",
    OrderBy.TITLE: "per nome festa",
    OrderBy.TYPE: "per tipo festa",
    OrderBy.REGION: "per stato/regione",
}


def extract_order_by(args: List[str]) -> List:
    # for now, this is only used for /events so the args order is preserved
    # and we can safely assume it from the args list

    args = [a.lower() for a in args]
    order_by = []

    for arg in args:
        if arg == OrderBy.DATE:
            order_by.extend([
                Event.start_year,
                Event.start_month,
                Event.start_day
            ])
        elif arg == OrderBy.WEEK_NUMBER:
            order_by.append(Event.start_week)
        elif arg == OrderBy.TYPE:
            order_by.append(Event.event_type)
        elif arg == OrderBy.TITLE:
            order_by.append(Event.event_title)
        elif arg == OrderBy.REGION:
            order_by.append(Event.region)

    if not order_by:
        # If no OrderBy arg, return the default ordering, based on EventFilter
        # We might want to adjust the records' sorting for some EventFilter
        # that is *not* an OrderBy filter
        # For example, for EventFilter.WEEK we might want to order the events first by region and then by date
        # We do this only if no order by filter is provided (that is, 'order_by' is empty)

        if EventFilter.WEEK in args:
            logger.info(f"default ordering for event filter <{EventFilter.WEEK}>")

            # week filter: we sort by region first
            order_by = [
                Event.region,
                Event.start_year,
                Event.start_month,
                Event.start_day,
                Event.event_title,
                Event.message_id
            ]
        else:
            logger.debug("default ordering")
            order_by = [
                Event.start_year,
                Event.start_month,
                Event.start_week,
                Event.region,
                Event.start_day,
                Event.event_title,
                Event.message_id
            ]

    # if we group by a specific Event property, we need the records to be ordered by that property *first*
    order_by_from_group_by = []
    for arg in args:
        if arg in (GroupBy.WEEK_NUMBER, GroupBy.MONTH, GroupBy.REGION):
            if arg == GroupBy.WEEK_NUMBER:
                order_by_from_group_by = [Event.start_year, Event.start_month, Event.start_week]
            elif arg == GroupBy.MONTH:
                order_by_from_group_by = [Event.start_year, Event.start_month]
            elif arg == GroupBy.REGION:
                order_by_from_group_by = [Event.region]
            else:
                order_by_from_group_by = []

            # exit the loop after the firsr occurrence
            break

    return order_by_from_group_by + order_by  # duplicates don't break the query


class GroupBy:
    WEEK_NUMBER = "gbw"
    MONTH = "gbm"
    REGION = "gbr"


GROUP_BY_DESCRIPTION = {
    GroupBy.WEEK_NUMBER: "per settimana inizio",
    GroupBy.MONTH: "per mese",
    GroupBy.REGION: "per stato/regione",
}


def extract_group_by(args: List[str]) -> str:
    # for now, this is only used for /events so the args order is preserved
    # we return the first group by key that is found

    for arg in args:
        arg = arg.lower()

        if arg in (GroupBy.WEEK_NUMBER, GroupBy.MONTH, GroupBy.REGION):
            return arg

    return ""


def events_to_dict(events_list: Sequence[Event], group_by_key: Optional[str] = None) -> Dict[str, List]:
    events_group_by_week = {}

    event: Event
    for event in events_list:
        if not event.is_valid():
            logger.info(f"skipping invalid event: {event}")
            continue

        if group_by_key == GroupBy.WEEK_NUMBER:
            if event.start_date:
                week_start, week_end = utilities.get_week_start_end(event.start_date)
                monday_str = utilities.format_datetime(week_start, format_str='%d ') + MONTHS_IT[week_start.month - 1][:3].lower()
                sunday_str = utilities.format_datetime(week_end, format_str='%d ') + MONTHS_IT[week_end.month - 1][:3].lower()
                key = f"Settimana {monday_str.lstrip('0')} ➜ {sunday_str.lstrip('0')}:"  # ➜
            else:
                key = f"{MONTHS_IT[event.start_month - 1]} {event.start_year}, senza data:"
        elif group_by_key == GroupBy.MONTH:
            key = f"{MONTHS_IT[event.start_month - 1]} {event.start_year}:"
        elif group_by_key == GroupBy.REGION:
            if event.region:
                emoji = REGIONS_DATA[event.region]["emoji"]
                key = f"{emoji} {event.region}:"
            else:
                key = f"Ignota:"
        else:
            # unknown or empty group_by_key: do not group by items
            key = f""

        if key in events_group_by_week:
            events_group_by_week[key].append(event)
        else:
            events_group_by_week[key] = [event]

    return events_group_by_week


def get_all_events_strings_from_db(session: Session, args: List[str], date_override: Optional[datetime.date] = None) -> List[str]:
    logger.debug("getting events from db...")

    query_filters = extract_query_filters(args, today=date_override)
    order_by = extract_order_by(args)  # returns an empty list if no elegible arg is provided

    events_list: List[Event] = events.get_events(session, filters=query_filters, order_by=order_by)

    all_events_strings = []
    total_entities_count = 0  # total number of telegram entities for the list of events
    formatting = EventFormatting()
    for i, event in enumerate(events_list):
        if not event.is_valid():
            logger.info(f"skipping invalid event: {event}")
            continue

        text_line, event_entities_count = format_event_string(event, formatting)
        all_events_strings.append(text_line)
        total_entities_count += event_entities_count  # not used yet, find something to do with this

    return all_events_strings


def get_all_events_strings_from_db_group_by(
        session: Session, args: List[str],
        date_override: Optional[datetime.date] = None,
        formatting: Optional[EventFormatting] = None
) -> List[str]:
    logger.debug("getting events from db...")
    logger.debug(f"formatting: {formatting}")

    query_filters = extract_query_filters(args, today=date_override)
    order_by = extract_order_by(args)  # returns the default ordering if no elegible arg is provided
    group_by_key = extract_group_by(args)
    logger.info(f"group by key: {group_by_key}")

    events_list: List[Event] = events.get_events(session, filters=query_filters, order_by=order_by)
    events_dict = events_to_dict(events_list, group_by_key)

    all_events_strings = []
    total_entities_count = 0  # total number of telegram entities for the list of events
    for group_by, events_list in events_dict.items():
        if group_by:
            # 'group_by' might be an empty string: do not apply grouping headers

            header_line = f"\n<b>{group_by}</b>"
            all_events_strings.append(header_line)
            total_entities_count += utilities.count_html_entities(header_line)

        event: Event
        for event in events_list:
            text_line, event_entities_count = format_event_string(event, formatting)
            all_events_strings.append(text_line)
            total_entities_count += event_entities_count  # not used yet, find something to do with this

    return all_events_strings
