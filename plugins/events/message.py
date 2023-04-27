import datetime
import logging
import re
from re import Match
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from telegram import Update, Message
from telegram.ext import ContextTypes, filters, MessageHandler

from database.models import Chat, Event
from database.queries import settings, events
import decorators
import utilities
from constants import BotSettingKey, Group, Regex
from config import config

logger = logging.getLogger(__name__)


events_chat_filter = filters.Chat(config.events.chat_id) & (filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE | filters.UpdateType.CHANNEL_POST | filters.UpdateType.EDITED_CHANNEL_POST)

FIRST_LINE_REGEX = r"^(.+)$"


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
    if message.effective_attachment and (
            message.effective_attachment.file_unique_id or isinstance(message.effective_attachment, list)):
        if isinstance(message.effective_attachment, list):
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

    title_match = re.search(FIRST_LINE_REGEX, message_text, re.M)
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

    session.commit()

    await update.effective_message.reply_text(f"{event.dates_str()}")


HANDLERS = (
    (MessageHandler(events_chat_filter, on_event_message), Group.PREPROCESS),
)
