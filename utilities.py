import datetime
import difflib
import hashlib
import json
import logging
import logging.config
import math
import re
import sys
from html import escape
from re import Match
from typing import List
from typing import Union, Optional, Tuple

import pytz
from pytz.tzinfo import StaticTzInfo, DstTzInfo
from telegram import User, Update, Chat, InlineKeyboardButton, KeyboardButton, Message, ChatMemberUpdated, \
    ChatMember, Bot
from telegram.error import BadRequest

from config import config
from constants import COMMAND_PREFIXES, Language, Regex, MediaType

logger = logging.getLogger(__name__)


UTC_TIMEZONE = datetime.timezone.utc

ROME_TIMEZONE = pytz.timezone("Europe/Rome")


def load_logging_config(file_name='logging.json'):
    with open(file_name, 'r') as f:
        logging_config = json.load(f)

    logging.config.dictConfig(logging_config)


def escape_html(string):
    return escape(str(string))


def mention_escaped(user: User, full_name=True) -> str:
    name = user.full_name if full_name else user.first_name
    return user.mention_html(name=escape_html(name))


def naive_to_aware(unaware: [datetime.datetime, datetime.date], force_utc=False):
    """returns the timezone-aware utc version of that datetime if naive or 'force_utc' is true,
    otherwise return the datetime itself"""

    # https://stackoverflow.com/a/41624199
    # https://www.skytowner.com/explore/python_datetime_timezone_aware_and_naive

    if unaware.tzinfo is not None and not force_utc:
        # the datetime object is timezone-aware
        return unaware

    # or: return unaware.replace(tzinfo=pytz.UTC)
    return pytz.utc.localize(unaware)


def now(tz: Optional[Union[str, bool, StaticTzInfo, DstTzInfo]] = None) -> datetime.datetime:
    """Returns the current datetime. A timezone can be passed as string, pytz.timezone(), or 'true' for Rome's timezone.
    If no argument is passed, the utc datetime is returned"""

    if not tz:
        return datetime.datetime.now(UTC_TIMEZONE)

    if isinstance(tz, bool) and tz is True:
        tz = ROME_TIMEZONE
    elif isinstance(tz, str):
        tz = pytz.timezone(tz)

    return datetime.datetime.now(tz=tz)


def now_str(format_str: Optional[str] = "%d/%m/%Y %H:%M:%S", tz: Optional[Union[str, bool, StaticTzInfo, DstTzInfo]] = None):
    return now(tz).strftime(format_str)


def format_datetime(dt_object: datetime.datetime, if_none="-", format_str: str = "%d/%m/%Y %H:%M:%S"):
    if not dt_object:
        return if_none

    return dt_object.strftime(format_str)


def is_test_bot():
    return "is_test_bot" in config.telegram and config.telegram.is_test_bot


def next_weekday(today: Optional[datetime.date] = None, weekday=0, additional_days: int = 0):
    """returns the datetime.date of the next monday, plus `additional_days` if provided"""

    if not today:
        today = datetime.date.today()

    days_ahead = weekday - today.weekday()
    if days_ahead <= 0:  # target day already happened this week
        days_ahead += 7

    return today + datetime.timedelta(days_ahead + additional_days)


def previous_weekday(today: Optional[datetime.date] = None, weekday=0):
    """returns the datetime.date of the last monday"""

    if not today:
        today = datetime.date.today()

    days_behind = today.weekday() - weekday
    if days_behind < 0:  # target day already happened this week
        days_behind += 7

    return today - datetime.timedelta(days_behind)


def is_superadmin(user: User) -> bool:
    return user.id in config.telegram.admins


def is_normal_group(chat: Chat) -> bool:
    # return str(chat.id).startswith("-100")
    return chat.type == Chat.GROUP


def forward_from_hidden_account(message: Message):
    return message.forward_sender_name and not message.forward_from


def is_service_account(user: User):
    return user.id in (777000,)


def is_forward_from_user(message: Message, exclude_service=True, exclude_bots=True):
    """Returns True if the original sender of the message was an user account. Will exlcude service account"""

    if message.forward_from and exclude_service and is_service_account(message.forward_from):
        return False
    elif message.forward_from and exclude_bots and message.forward_from.is_bot:
        # message.forward_from always exist with bots because they cannot hide their forwards
        return False

    # return True even when the user decided to hide their account
    return message.forward_sender_name or message.forward_from


def is_organic_user(user: User):
    return not (is_service_account(user) or user.is_bot)


def is_reply_to_user(message: Message, not_self=False) -> bool:
    if not message.reply_to_message:
        return False

    replied_message = message.reply_to_message
    if not replied_message.from_user:
        return False

    if replied_message.from_user.is_bot:
        return False

    if is_service_account(replied_message.from_user):
        return False

    if not_self and message.from_user and message.from_user.id == replied_message.from_user.id:
        return False

    return True


def is_join_update(chat_member_update: ChatMemberUpdated):
    not_member_statuses = (ChatMember.LEFT, ChatMember.BANNED)
    member_statuses = (ChatMember.MEMBER, ChatMember.RESTRICTED, ChatMember.ADMINISTRATOR, ChatMember.OWNER)

    return chat_member_update.old_chat_member.status in not_member_statuses and chat_member_update.new_chat_member.status in member_statuses


def is_left_update(chat_member_update: ChatMemberUpdated) -> bool:
    if chat_member_update.from_user != chat_member_update.new_chat_member.user.id:
        # performer of the action (chat_member_update.from_user) != user that changed status: user was kicked (didn't leave)
        return False

    member_statuses = (ChatMember.MEMBER, ChatMember.RESTRICTED, ChatMember.ADMINISTRATOR, ChatMember.OWNER)

    return chat_member_update.old_chat_member.status in member_statuses and chat_member_update.new_chat_member.status == ChatMember.LEFT


def is_kicked_update(chat_member_update: ChatMemberUpdated) -> bool:
    if chat_member_update.from_user == chat_member_update.new_chat_member.user.id:
        # performer of the action (chat_member_update.from_user) == user that changed status: user left (not kicked)
        return False

    member_statuses = (ChatMember.MEMBER, ChatMember.RESTRICTED, ChatMember.ADMINISTRATOR, ChatMember.OWNER)

    return chat_member_update.old_chat_member.status in member_statuses and chat_member_update.new_chat_member.status == ChatMember.LEFT


def is_unban_update(chat_member_update: ChatMemberUpdated) -> bool:
    if chat_member_update.from_user == chat_member_update.new_chat_member.user.id:
        # performer of the action (chat_member_update.from_user) == user that changed status: user left (not kicked)
        return False

    banned_statuses = (ChatMember.BANNED,)

    return chat_member_update.old_chat_member.status in banned_statuses and chat_member_update.new_chat_member.status == ChatMember.LEFT


def extract_invite_link_id(invite_link: str) -> str:
    match = re.search(r"t\.me/\+(?P<invite_link>\w+)\b", invite_link, re.I)
    return match.group("invite_link")


def is_reply_to_forwarded_channel_message(message: Message) -> bool:
    if not message.reply_to_message:
        return False

    return message.reply_to_message.forward_from_chat and message.reply_to_message.forward_from_chat.type == Chat.CHANNEL


def detect_media_type(message: Message, raise_on_unknown_type=True) -> Optional[str]:
    if message.photo:
        return MediaType.PHOTO
    elif message.video:
        return MediaType.VIDEO
    elif message.animation:
        # must be before the 'document' check because message.document is also populated for gifs
        return MediaType.ANIMATION
    elif message.document:
        return MediaType.DOCUMENT
    elif message.voice:
        return MediaType.VOICE
    elif message.video_note:
        return MediaType.VIDEO_NOTE
    elif message.audio:
        return MediaType.AUDIO
    elif message.sticker:
        return MediaType.STICKER

    if raise_on_unknown_type:
        raise ValueError("message contains unknown media type or doesn't contain a media")

    return


async def reply_media(message: Message, media_type: str, file_id: str, caption: Optional[str] = None, quote: Optional[bool] = None) -> Message:
    if media_type == MediaType.PHOTO:
        return await message.reply_photo(file_id, caption=caption, quote=quote)
    elif media_type == MediaType.VIDEO:
        return await message.reply_video(file_id, caption=caption, quote=quote)
    elif media_type == MediaType.DOCUMENT:
        return await message.reply_document(file_id, caption=caption, quote=quote)
    elif media_type == MediaType.VOICE:
        return await message.reply_voice(file_id, caption=caption, quote=quote)
    elif media_type == MediaType.VIDEO_NOTE:
        return await message.reply_video_note(file_id, quote=quote)
    elif media_type == MediaType.AUDIO:
        return await message.reply_audio(file_id, caption=caption, quote=quote)
    elif media_type == MediaType.ANIMATION:
        return await message.reply_animation(file_id, caption=caption, quote=quote)
    elif media_type == MediaType.STICKER:
        return await message.reply_sticker(file_id, quote=quote)


def contains_media_with_file_id(message: Message):
    return message.effective_attachment and (isinstance(message.effective_attachment, tuple) or message.effective_attachment.file_unique_id)


def get_media_ids(message: Message):
    media_file_id = None
    media_file_unique_id = None
    media_group_id = message.media_group_id

    if isinstance(message.effective_attachment, tuple):
        media_file_id = message.effective_attachment[-1].file_id
        media_file_unique_id = message.effective_attachment[-1].file_unique_id
    else:
        media_file_id = message.effective_attachment.file_id
        media_file_unique_id = message.effective_attachment.file_unique_id

    return media_file_id, media_file_unique_id, media_group_id


def get_user_id_from_text(text: str) -> Optional[int]:
    match = re.search(Regex.USER_ID_HASHTAG, text, re.I)
    if not match:
        return

    return int(match.group("user_id"))


def generate_text_hash(text: str) -> str:
    # https://stackoverflow.com/a/3739928
    text_no_whitespaces = re.sub(r'(\s|\u180B|\u200B|\u200C|\u200D|\u2060|\uFEFF)+', '', text)
    md5_string = hashlib.md5(text_no_whitespaces.encode('utf-8')).hexdigest()

    return md5_string


def get_argument(commands: Union[List, str], text: str, remove_user_id_hashtag=False) -> str:
    if isinstance(commands, str):
        commands = [commands]

    prefixes = "".join(COMMAND_PREFIXES)

    for command in commands:
        text = re.sub(rf"^[{prefixes}]{command}\s*", "", text, re.I)

    if remove_user_id_hashtag:
        text = re.sub(Regex.USER_ID_HASHTAG_SUB, "", text)

    return text.strip()


def get_command(text: str, lower=True) -> str:
    prefixes = "".join(COMMAND_PREFIXES)

    text = re.search(rf"^[{prefixes}](\w+)\s*", text, re.I).group(1)

    text = text.strip()
    if lower:
        text = text.lower()

    return text


def count_html_entities(string: str) -> int:
    return len(re.findall(r"(<(?:b|i|u|s|code)>|<a href=)", string))


def get_language_code(selected_language_code, telegram_language_code):
    if selected_language_code:
        return selected_language_code

    return telegram_language_code or Language.EN


async def delete_messages_safe(messages: Union[Message, List[Message]]):
    if not isinstance(messages, list):
        messages = [messages]

    for message in messages:
        try:
            await message.delete()
        except BadRequest:
            pass


async def delete_messages_by_id_safe(bot: Bot, chat_id: int, message_ids: Union[List[int], int]) -> Optional[bool]:
    """returns the request result if only one message_id was passed, otherwise None"""

    if not isinstance(message_ids, list):
        message_ids = [message_ids]

    success = None
    for message_id in message_ids:
        try:
            # delete_message will return true even when the message has already been deleted from the chat
            # (even by someone else)
            success = await bot.delete_message(chat_id, message_id)
        except BadRequest as e:
            logger.debug(f"error while deleting message {message_id} in chat {chat_id}: {e}")
            if "message can't be deleted" in e.message.lower():
                success = False

    if len(message_ids) == 1:
        return success


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


def log_string_chat(chat: Chat) -> str:
    return f"{chat.type} {chat.id} ({chat.title})"


def log_string_user(user: User) -> str:
    return f"{user.id} ({user.full_name}; lang: {user.language_code})"


def log(update: Update):
    try:
        if update.callback_query:
            return f"from {log_string_user(update.effective_user)}, cbdata: {update.callback_query.data}"
        elif update.effective_message:
            if update.effective_chat.type in (Chat.SUPERGROUP, Chat.GROUP):
                if update.effective_message.sender_chat:
                    # message is a group message, but the sender is a chat
                    return f"from {log_string_chat(update.effective_message.sender_chat)} in {log_string_chat(update.effective_chat)}"
                else:
                    return f"from {log_string_user(update.effective_user)} in {log_string_chat(update.effective_chat)}"
            elif update.effective_chat.type == Chat.CHANNEL:
                return f"in {log_string_chat(update.effective_chat)}"
            elif update.effective_chat.type == Chat.PRIVATE:
                return f"from {log_string_user(update.effective_user)}"
        elif update.chat_member or update.my_chat_member:
            chat_member = update.chat_member or update.my_chat_member
            return f"from {log_string_user(chat_member.from_user)} in {log_string_chat(chat_member.chat)}"
    except Exception as e:
        logger.error(f"error while logging update: {e}")


def is_leap_year(year):
    return ((year % 400 == 0) and (year % 100 == 0)) or ((year % 4 == 0) and (year % 100 != 0))


def format_year(year: Optional[str] = None) -> int:
    if year:
        if len(year) == 2:
            year = f"20{year}"
    else:
        year = datetime.datetime.now().year

    year = int(year)

    return year


def check_day(day: int, month: int, year: int):
    if month in (1, 3, 5, 7, 8, 10, 12) and not (1 <= day <= 31):
        raise ValueError("provided day must be in 1..31")
    if month in (4, 6, 9, 11) and not (1 <= day <= 30):
        raise ValueError("provided day must be in 1..30")
    if month == 2:
        if is_leap_year(year) and not (1 <= day <= 29):
            raise ValueError("provided day must be in 1..29")
        elif not is_leap_year(year) and not (1 <= day <= 28):
            raise ValueError("provided day must be in 1..28")


def check_month(month: int):
    if not (1 <= month <= 12):
        raise ValueError("provided month must be in 1..12")


def date_from_match(match: Match):
    day = int(match.group("day"))
    month = int(match.group("month"))
    year = match.group("year")
    year = format_year(year)

    check_day(day, month, year)

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

    if re.search(r"^-?\d+$", value):
        return int(value)

    if re.match(r'^-?\d+(?:[\.,]\d+)$', value):
        # https://stackoverflow.com/a/736050
        return float(value)

    match = re.match(Regex.DATETIME, value, re.I)
    if match:
        day, month, year = date_from_match(match)
        second, minute, hour = time_from_match(match)
        return datetime.datetime(day=day, month=month, year=year, hour=hour, minute=minute, second=second)

    match = re.match(Regex.DATE, value, re.I)
    if match:
        day, month, year = date_from_match(match)
        return datetime.date(day=day, month=month, year=year)

    return value


def extract_entity(text: str, offset: int, length: int) -> str:
    # Is it a narrow build, if so we don't need to convert
    if sys.maxunicode == 0xFFFF:
        return text[offset: offset + length]

    entity_text = text.encode("utf-16-le")
    entity_text = entity_text[offset * 2: (offset + length) * 2]
    return entity_text.decode("utf-16-le")


def unpack_message_link(message_link: str) -> Tuple[Optional[Union[int, str]], Optional[int]]:
    match = re.search(
        Regex.MESSAGE_LINK,
        message_link,
        re.I
    )
    if not match:
        return None, None

    message_id = int(match.group("message_id"))
    chat_id = match.group("chat_id")
    if not chat_id:
        chat_id = f"@{match.group('username')}"
    else:
        chat_id = int(f"-100{chat_id}")

    return chat_id, message_id


def diff(string1: str, string2: str):
    lines1 = string1.strip().splitlines()
    lines2 = string2.strip().splitlines()

    output_lines = []
    for line in difflib.unified_diff(lines1, lines2, lineterm=''):
        output_lines.append(line)

    return "\n".join(output_lines)


def diff_alt(string1: str, string2: str, ignore_empty_lines_diff=True, ignore_context_lines=False):
    lines1 = string1.strip().splitlines()
    lines2 = string2.strip().splitlines()

    output_lines = []
    for line in difflib.unified_diff(lines1, lines2, lineterm='', n=0):
        if ignore_context_lines and line.startswith(('---', '+++', '@@')):
            continue

        if ignore_empty_lines_diff and not re.sub(r"^(\+|-)", "", line.strip()):
            continue

        output_lines.append(line)

    return "\n".join(output_lines)


if __name__ == "__main__":
    # print(convert_string_to_value("29/02/32 10:59"))
    # test_keyboard = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"]
    # list_to_keyboard(test_keyboard, max_rows=4)
    today_date = datetime.date(2023, 4, 30)
    print(previous_weekday(today_date), next_weekday(today_date))

