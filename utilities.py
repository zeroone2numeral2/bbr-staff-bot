import datetime
import json
import logging
import logging.config
import math
import re
from html import escape
from re import Match
from typing import Union
from typing import List

from telegram import User, Update, Chat, InlineKeyboardButton, KeyboardButton
from telegram.error import BadRequest

from config import config
from constants import COMMAND_PREFIXES, Language

logger = logging.getLogger(__name__)


def load_logging_config(file_name='logging.json'):
    with open(file_name, 'r') as f:
        logging_config = json.load(f)

    logging.config.dictConfig(logging_config)


def escape_html(string):
    return escape(str(string))


def now():
    return datetime.datetime.utcnow()


def is_admin(user: User) -> bool:
    return user.id in config.telegram.admins


def is_normal_group(chat: Chat) -> bool:
    # return str(chat.id).startswith("-100")
    return chat.type == Chat.GROUP


def get_argument(commands: Union[List, str], text: str) -> str:
    if isinstance(commands, str):
        commands = [commands]

    prefixes = "".join(COMMAND_PREFIXES)

    for command in commands:
        text = re.sub(rf"^[{prefixes}]{command}\s*", "", text, re.I)

    return text.strip()


def get_command(text: str) -> str:
    prefixes = "".join(COMMAND_PREFIXES)

    text = re.search(rf"^[{prefixes}](\w+)\s*", text, re.I).group(1)

    return text.strip()


def get_language_code(selected_language_code, telegram_language_code):
    if selected_language_code:
        return selected_language_code

    return telegram_language_code or Language.EN


async def edit_text_safe(update: Update, *args, **kwargs):
    try:
        await update.effective_message.edit_text(*args, **kwargs)
    except BadRequest as e:
        if "message is not modified" not in e.message.lower():
            raise e


async def remove_reply_markup_safe(bot, chat_id: int, message_id: int):
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except BadRequest as e:
        if "message is not modified" not in e.message.lower():
            raise e


def user_log(user: User):
    return f"{user.id} ({user.full_name} [{user.language_code}])"


def chat_log(chat: Chat):
    return f"{chat.id} ({chat.title})"


def list_to_keyboard(
        keyboard: List[Union[InlineKeyboardButton, KeyboardButton]],
        max_rows: int
) -> List[List[Union[InlineKeyboardButton, KeyboardButton]]]:
    num_rows = len(keyboard)
    if num_rows <= max_rows:
        return [[button] for button in keyboard]

    if num_rows % max_rows == 0:
        num_columns = int(num_rows / max_rows)
    else:
        num_columns = math.floor(num_rows / max_rows) + 1

    # print(f"{num_rows} -> {num_columns}x{max_rows}")

    new_keyboard = []
    for row_num in range(max_rows):
        start_index = row_num * num_columns
        new_row = keyboard[start_index:start_index+num_columns]
        new_keyboard.append(new_row)
        # print(f"[{start_index}:{start_index + num_columns}] -> {new_row}")

    # print(new_keyboard)
    return new_keyboard


def log_old(obj: Union[User, Chat]):
    if isinstance(obj, User):
        return user_log(obj)
    elif isinstance(obj, Chat):
        return chat_log(obj)


def log(update: Update):
    try:
        if update.message:
            if update.effective_chat.id != update.effective_user.id:
                # group chat
                return f"from {update.effective_user.id} ({update.effective_user.full_name}; lang: {update.effective_user.language_code})" \
                       f" in {update.effective_chat.id} ({update.effective_chat.title})"
            else:
                # private chat
                return f"from {update.effective_user.id} ({update.effective_user.full_name}; lang: {update.effective_user.language_code})"
        elif update.callback_query:
            return f"from {update.effective_user.id} ({update.effective_user.full_name}; lang: {update.effective_user.language_code}), cbdata: {update.callback_query.data}"
        elif update.chat_member or update.my_chat_member:
            chat_member = update.chat_member or update.my_chat_member
            return f"from {chat_member.from_user.id} ({chat_member.from_user.full_name}) " \
                   f"in {chat_member.chat.id} ({chat_member.chat.title})"
    except Exception as e:
        logger.error(f"error while logging update: {e}")


def is_leap_year(year):
    return ((year % 400 == 0) and (year % 100 == 0)) or ((year % 4 == 0) and (year % 100 != 0))


def date_from_match(match: Match):
    day = int(match.group("day"))
    month = int(match.group("month"))
    year = match.group("year")
    if year:
        if len(year) == 2:
            year = f"20{year}"
    else:
        year = datetime.datetime.now().year

    year = int(year)

    if not (1 <= month <= 12):
        raise ValueError("provided month must be in 1..12")
    if month in (1, 3, 5, 7, 8, 10, 12) and not (1 <= day <= 31):
        raise ValueError("provided day must be in 1..31")
    if month in (4, 6, 9, 11) and not (1 <= day <= 30):
        raise ValueError("provided day must be in 1..30")
    if month == 2:
        if is_leap_year(year) and not (1 <= day <= 29):
            raise ValueError("provided day must be in 1..29")
        elif not is_leap_year(year) and not (1 <= day <= 28):
            raise ValueError("provided day must be in 1..28")

    return int(day), int(month), int(year)


def time_from_match(match: Match):
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second")) if match.group("second") else 0

    if not (0 <= hour <= 23):
        raise ValueError("provided hour must be in 0..23")
    if not (0 <= minute <= 59):
        raise ValueError("provided minute must be in 0..59")
    if not (0 <= second <= 59):
        raise ValueError("provided second must be in 0..59")

    return second, minute, hour


def convert_string_to_value(value):
    if value.lower() in ("true", "false"):
        return value.lower() == "true"

    if value.lower() in ("none", "null"):
        return None

    if re.search(r"^\d+$", value):
        return int(value)

    if re.match(r'^-?\d+(?:[\.,]\d+)$', value):
        # https://stackoverflow.com/a/736050
        return float(value)

    datetime_regex = r"(?P<date>(?P<day>\d{1,2})[/.-](?P<month>\d{1,2})(?:[/.-](?P<year>\d{2,4}))?)\s+((?P<hour>\d{1,2}):(?P<minute>\d{1,2})(?::(?P<second>\d{1,2}))?)"
    match = re.match(datetime_regex, value, re.I)
    if match:
        day, month, year = date_from_match(match)
        second, minute, hour = time_from_match(match)
        return datetime.datetime(day=day, month=month, year=year, hour=hour, minute=minute, second=second)

    date_regex = r"(?P<day>\d{1,2})[/.-](?P<month>\d{1,2})(?:[/.-](?P<year>\d{2,4}))?"
    match = re.match(date_regex, value, re.I)
    if match:
        day, month, year = date_from_match(match)
        return datetime.date(day=day, month=month, year=year)

    return value


if __name__ == "__main__":
    # print(convert_string_to_value("29/02/32 10:59"))
    test_keyboard = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"]
    list_to_keyboard(test_keyboard, max_rows=4)

