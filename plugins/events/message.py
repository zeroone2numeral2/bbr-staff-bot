import datetime
import logging
import re
from re import Match
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session
from telegram import Update, Message, MessageEntity
from telegram.ext import ContextTypes, filters, MessageHandler, CommandHandler

from database.models import Chat, Event, EventTypeHashtag, EVENT_TYPE, User
from database.queries import settings, events
import decorators
import utilities
from constants import BotSettingKey, Group, Regex, REGIONS_DATA
from config import config

logger = logging.getLogger(__name__)


events_chat_filter = filters.Chat(config.events.chat_id) & (filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE | filters.UpdateType.CHANNEL_POST | filters.UpdateType.EDITED_CHANNEL_POST)


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


def date_from_match(match: Match):
    start_day_str = match.group("start_day")
    if "?" in start_day_str:
        start_day = None
    else:
        start_day = int(start_day_str)

    month = int(match.group("month"))
    year = match.group("year")
    if year:
        if len(year) == 2:
            year = f"20{year}"
    else:
        year = datetime.datetime.now().year

    year = int(year)

    # check month
    if not (1 <= month <= 12):
        raise ValueError("provided month must be in 1..12")

    # check day
    if start_day is not None:
        check_day(start_day, month, year)

    dates_dict = dict(start_date=(start_day, month, year), end_date=None)

    end_day_str = match.group("end_day")
    if end_day_str:
        if "?" not in end_day_str:
            end_day = int(end_day_str)
            check_day(end_day, month, year)

            end_month = month
            if end_day < start_day:
                # end day is next month: add one month to date_end
                end_month += 1

            dates_dict["end_date"] = (end_day, end_month, year)
        else:
            dates_dict["end_date"] = (None, month, year)

    return dates_dict


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

    hashtags_dict = message.parse_entities(MessageEntity.HASHTAG) if message.text else message.parse_caption_entities(MessageEntity.HASHTAG)
    hashtags_list = [v.lower() for v in hashtags_dict.values()]
    event.save_hashtags(hashtags_list)
    for hashtag, event_type in EVENT_TYPE.items():
        if hashtag in hashtags_list:
            event.event_type = event_type

    if "#annullata" in hashtags_list or "#annullato" in hashtags_list:
        event.canceled = True

    for region_name, region_data in REGIONS_DATA.items():
        for region_hashtag in region_data["hashtags"]:
            if region_hashtag in hashtags_list:
                event.region = region_name
                # return after the first match
                break

    title_match = re.search(Regex.FIRST_LINE, message_text, re.M)
    if title_match:
        event.event_title = title_match.group(1)
    else:
        logger.info("couldn't parse any title")

    date_match = re.search(Regex.EVENT_DATE, message_text, re.M)
    if not date_match:
        logger.info("couldn't parse any date with regex")
    else:
        try:
            dates_dict = date_from_match(date_match)
            event.start_day = dates_dict["start_date"][0]
            event.start_month = dates_dict["start_date"][1]
            event.start_year = dates_dict["start_date"][2]
            if dates_dict["end_date"] is not None:
                event.end_day = dates_dict["end_date"][0]
                event.end_month = dates_dict["end_date"][1]
                event.end_year = dates_dict["end_date"][2]
        except ValueError as e:
            logger.info(f"error while parsing date: {e}")


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
@decorators.pass_session(pass_user=True)
async def on_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/events {utilities.log(update)}")

    events_list: List[Event] = events.get_events(session, config.events.chat_id)
    text_lines = []
    for i, event in enumerate(events_list):
        if not event.is_valid():
            logger.info(f"skipping invalid event: {event}")
            continue

        region_icon = ""
        if event.region and event.region in REGIONS_DATA:
            region_icon = REGIONS_DATA[event.region]["emoji"]

        title_escaped = utilities.escape_html(event.event_title)
        text_line = f"{event.icon()}{region_icon} <b>{title_escaped}</b> ({event.pretty_date()}) <a href=\"{event.message_link()}\">--fly/info</a>"
        text_lines.append(text_line)

        if i > 49:
            # max 100 entities per message
            break

    await update.message.reply_text("\n".join(text_lines))


HANDLERS = (
    (MessageHandler(events_chat_filter, on_event_message), Group.PREPROCESS),
    (CommandHandler("events", on_events_command), Group.NORMAL),
)
