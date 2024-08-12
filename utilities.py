import datetime
import difflib
import hashlib
import json
import logging
import logging.config
import math
import re
import sys
from functools import partial
from html import escape
from re import Match
from typing import List
from typing import Union, Optional, Tuple
from pprint import pprint

import pytz
from pytz.tzinfo import StaticTzInfo, DstTzInfo
from telegram import User, Update, Chat, InlineKeyboardButton, KeyboardButton, Message, ChatMemberUpdated, \
    ChatMember, Bot, MessageOriginUser, MessageOriginHiddenUser, MessageOriginChannel, ReplyParameters
from telegram.constants import MessageType, ChatAction, ParseMode
from telegram.error import BadRequest, TelegramError, Forbidden
from telegram.helpers import effective_message_type

from config import config
from constants import COMMAND_PREFIXES, Language, Regex

logger = logging.getLogger(__name__)


UTC_TIMEZONE = datetime.timezone.utc

ROME_TIMEZONE = pytz.timezone("Europe/Rome")

SUPERSCRIPT = str.maketrans(
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_",
    "⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᵠʳˢᵗᵘᵛʷˣʸᶻᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᵠʳˢᵗᵘᵛʷˣʸᶻ‾"
)

SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")

CAPTIONABLE_TYPES = (
    MessageType.ANIMATION,
    MessageType.AUDIO,
    MessageType.DOCUMENT,
    MessageType.PHOTO,
    MessageType.VIDEO,
    MessageType.VOICE,
)

SUPPORT_SPOILER_TYPES = (
    MessageType.PHOTO,
    MessageType.VIDEO,
    MessageType.ANIMATION,
)


def load_logging_config(file_name='logging.json'):
    with open(file_name, 'r') as f:
        logging_config = json.load(f)

    logging.config.dictConfig(logging_config)


def escape_html(string):
    return escape(str(string))


def html_url(text: str, url: str):
    """returns the html url behind the given text. the text will always be escaped"""

    return f"<a href=\"{url}\">{escape_html(text)}</a>"


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


def now(tz: Optional[Union[str, bool, StaticTzInfo, DstTzInfo]] = None, dst_check=False) -> datetime.datetime:
    """Returns the current datetime. A timezone can be passed as string, pytz.timezone(), or 'true' for Rome's timezone.
    If no argument is passed, the utc datetime is returned"""

    if not tz:
        return datetime.datetime.now(tz=UTC_TIMEZONE)

    now_naive = datetime.datetime.now()
    if isinstance(tz, bool) and tz is True:
        tz = ROME_TIMEZONE
    elif isinstance(tz, str):
        tz = pytz.timezone(tz)

    local_time = tz.localize(now_naive)
    if dst_check and local_time.dst() and False:
        return local_time + local_time.dst()

    return local_time


class SecondsQt:
    DAY = 24 * 60 * 60
    HOUR = 60 * 60
    MINUTE = 60


SECONDS_REDUCTION = {
    "anno": {"seconds": 365 * 24 * 60 * 60, "singular": "un ", "plural": "i", "short": "w", "skip": True},
    "settimana": {"seconds": 7 * 24 * 60 * 60, "singular": "una ", "plural": "e", "short": "w", "skip": True},
    "giorno": {"seconds": 24 * 60 * 60, "singular": "un ", "plural": "i", "short": "d", "skip": False},
    "ora": {"seconds": 60 * 60, "singular": "un'", "plural": "e", "short": "h", "skip": False},
    "minuto": {"seconds": 60, "singular": "un ", "plural": "i", "short": "m", "skip": True},
    "secondo": {"seconds": 1, "singular": "un ", "plural": "i", "short": "s", "skip": True},
}


def subscript(string: str) -> str:
    return string.translate(SUBSCRIPT)


def superscript(string: str) -> str:
    return string.translate(SUPERSCRIPT)


def text_contains(text: str, strings_to_check: Union[str, List[str]]) -> bool:
    if isinstance(strings_to_check, str):
        strings_to_check = [strings_to_check]

    for string in strings_to_check:
        if string.lower() in text.lower():
            return True

    return False


def round_base(n, base=1.0):
    return int(round(n / base) * base)


round_to_hour = partial(round_base, base=60.0)


def elapsed_str_from_seconds(total_seconds: int, if_empty: Optional[str] = None) -> str:
    string = ""
    for period, period_data in SECONDS_REDUCTION.items():
        if period_data["skip"]:
            continue

        elapsed_time = math.floor(total_seconds / period_data["seconds"])
        total_seconds -= elapsed_time * period_data["seconds"]

        if elapsed_time == 0:
            continue

        if string:
            string += ", "

        period_string = period if elapsed_time < 2 else period[:-1] + period_data["plural"]
        elapsed_time_str = f"{elapsed_time} " if elapsed_time > 1 else period_data["singular"]
        string += f"{elapsed_time_str}{period_string}"

    if not string and if_empty:
        # eg. a few seconds of difference and SECONDS_REDUCTION["secondo"]["skip"] is true
        return if_empty

    return string


def elapsed_str(from_dt: datetime.datetime, if_empty: Optional[str] = None) -> str:
    from_dt_utc = naive_to_aware(from_dt, force_utc=True)
    total_seconds = (now() - from_dt_utc).total_seconds()

    return elapsed_str_from_seconds(total_seconds, if_empty)


def elapsed_str_old(from_dt: datetime.datetime) -> str:
    from_dt_utc = naive_to_aware(from_dt, force_utc=True)
    total_seconds = (now() - from_dt_utc).total_seconds()

    elapsed_days = math.floor(total_seconds / SecondsQt.DAY)
    total_seconds -= elapsed_days * SecondsQt.DAY

    elapsed_hours = math.floor(total_seconds / SecondsQt.HOUR)
    total_seconds -= elapsed_hours * SecondsQt.HOUR

    elapsed_minutes = math.floor(total_seconds / SecondsQt.MINUTE)

    elapsed_seconds = int(total_seconds - (elapsed_minutes * SecondsQt.MINUTE))

    # print(f"{elapsed_days} d, {elapsed_hours} h, {elapsed_minutes} m, {elapsed_seconds} s")

    # "n hours ago" if hours > 0, else "n minutes ago"
    string = ""
    if elapsed_days >= 1:
        string += f"{math.floor(elapsed_days)} giorn{'i' if elapsed_days > 1 else 'o'}"

    if elapsed_hours >= 1:
        if string:
            string += ", "
        string += f"{math.floor(elapsed_hours)} or{'e' if elapsed_hours > 1 else 'a'}"

    if elapsed_days == 0 and elapsed_hours == 0 and elapsed_minutes:
        # include minutes only if no hour and day
        if string:
            string += ", "
        string += f"{math.floor(elapsed_minutes)} minut{'1' if elapsed_minutes > 1 else 'o'}"

    return string


def now_str(format_str: Optional[str] = "%d/%m/%Y %H:%M:%S", tz: Optional[Union[str, bool, StaticTzInfo, DstTzInfo]] = None):
    return now(tz).strftime(format_str)


def format_datetime(dt_object: Union[datetime.datetime, datetime.date], if_none="-", format_str: str = "%d/%m/%Y %H:%M:%S"):
    if not dt_object:
        return if_none

    return dt_object.strftime(format_str)


def _bool_to_str_base(value, true_str, false_str) -> str:
    if value:
        return true_str
    else:
        return false_str


def bool_to_str_it(value, si_no=False) -> str:
    return _bool_to_str_base(
        value,
        true_str="si" if si_no else "vero",
        false_str="no" if si_no else "falso"
    )


def bool_to_str(value, yes_no=False) -> str:
    return _bool_to_str_base(
        value,
        true_str="yes" if yes_no else "true",
        false_str="no" if yes_no else "false"
    )


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


def get_week_start_end(dt: datetime.date) -> Tuple[datetime.date, datetime.date]:
    monday = dt - datetime.timedelta(days=dt.weekday())
    sunday = monday + datetime.timedelta(days=6)

    return monday, sunday


def is_superadmin(user: User) -> bool:
    return user.id in config.telegram.admins


def copy_message_supported(message: Message):
    return effective_message_type(message) in (
        MessageType.ANIMATION,
        MessageType.AUDIO,
        MessageType.DICE,
        MessageType.DOCUMENT,
        MessageType.LOCATION,
        MessageType.PHOTO,
        MessageType.STICKER,
        MessageType.TEXT,
        MessageType.VIDEO,
        MessageType.VIDEO_NOTE,
        MessageType.VOICE,
    )


async def copy_message(
    bot: Bot,
    message: Message,
    chat_id: int,
    text_or_caption_override: Optional[str] = None,
    ignore_media: Optional[bool] = False,
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[int] = None,
    allow_sending_without_reply: Optional[bool] = None,
    protect_content: Optional[bool] = None,
    message_thread_id: Optional[int] = None,
    has_spoiler_ovverride: Optional[bool] = None,
    raise_on_unsupported_type=True
) -> Optional[Message]:
    message_type = effective_message_type(message)

    kwargs = dict(
        chat_id=chat_id,
        reply_markup=reply_markup,
        protect_content=protect_content,
        message_thread_id=message_thread_id,
    )

    if reply_to_message_id:
        kwargs["reply_parameters"] = ReplyParameters(
            message_id=reply_to_message_id,
            allow_sending_without_reply=allow_sending_without_reply
        )

    if message_type == MessageType.TEXT or ignore_media:
        if ignore_media and not message.caption:
            raise ValueError(f"ignore_media is true but the message doesn't have a caption")
        elif ignore_media:
            # send the message's caption (or override) as text
            kwargs["text"] = text_or_caption_override if text_or_caption_override is not None else message.caption_html
        else:
            # use the message's text (or override)
            kwargs["text"] = text_or_caption_override if text_or_caption_override is not None else message.text_html

        return await bot.send_message(**kwargs)

    if message_type in CAPTIONABLE_TYPES:
        if text_or_caption_override is not None:
            # for some reason, if 'text_or_caption_override' is an empty string, "[]" will be sent as caption,
            # so we need to set it to None
            kwargs["caption"] = text_or_caption_override if text_or_caption_override else None
        else:
            kwargs["caption"] = message.caption_html

    if message_type in SUPPORT_SPOILER_TYPES:
        kwargs["has_spoiler"] = has_spoiler_ovverride if has_spoiler_ovverride is not None else message.has_media_spoiler

    if message_type == MessageType.ANIMATION:
        result = await bot.send_animation(animation=message.animation.file_id, **kwargs)
    elif message_type == MessageType.AUDIO:
        result = await bot.send_audio(audio=message.audio.file_id, **kwargs)
    elif message_type == MessageType.DICE:
        result = await bot.send_dice(emoji=message.text, **kwargs)
    elif message_type == MessageType.DOCUMENT:
        result = await bot.send_document(document=message.document.file_id, **kwargs)
    elif message_type == MessageType.LOCATION:
        result = await bot.send_location(
            latitude=message.location.latitude,
            longitude=message.location.longitude,
            horizontal_accuracy=message.location.horizontal_accuracy,
            heading=message.location.heading,
            proximity_alert_radius=message.location.proximity_alert_radius,
            **kwargs
        )
    elif message_type == MessageType.PHOTO:
        result = await bot.send_photo(photo=message.photo[-1].file_id, **kwargs)
    elif message_type == MessageType.STICKER:
        result = await bot.send_sticker(sticker=message.sticker.file_id, **kwargs)
    elif message_type == MessageType.VIDEO:
        result = await bot.send_video(video=message.video.file_id, **kwargs)
    elif message_type == MessageType.VIDEO_NOTE:
        result = await bot.send_video_note(video_note=message.video_note.file_id, **kwargs)
    elif message_type == MessageType.VOICE:
        result = await bot.send_voice(voice=message.voice.file_id, **kwargs)
    else:
        if raise_on_unsupported_type:
            raise NotImplementedError(f"copying message of type '{message_type}' is not supported")
        else:
            return

    return result


def is_normal_group(chat: Chat) -> bool:
    # return str(chat.id).startswith("-100")
    return chat.type == Chat.GROUP


def forward_from_hidden_account(message: Message):
    return message.forward_origin and isinstance(message.forward_origin, MessageOriginHiddenUser)


def is_service_account(user: User):
    return user.id in (777000,)


def is_forward_from_user(message: Message, exclude_service_accounts=True, exclude_bots=True):
    """Returns True if the original sender of the message was an user account. Will exlcude service account by default"""

    if not message.forward_origin:
        # not a forwarded message
        return False

    if not isinstance(message.forward_origin, (MessageOriginUser, MessageOriginHiddenUser)):
        # not a forwarded message from an user/an user that hidden their identity
        return False

    if isinstance(message.forward_origin, MessageOriginHiddenUser):
        # return True even when the user decided to hide their account
        if exclude_service_accounts or exclude_bots:
            logger.info("origin sender hid their account: cannot check whether it is a bot or service account")

        return True

    if exclude_service_accounts and is_service_account(message.forward_origin.sender_user):
        return False
    elif exclude_bots and message.forward_origin.sender_user.is_bot:
        # message.forward_origin.sender_user always exist with bots because they cannot hide their forwards
        return False

    return True


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
    if chat_member_update.from_user.id != chat_member_update.new_chat_member.user.id:
        # performer of the action (chat_member_update.from_user) != user that changed status: user was kicked (didn't leave)
        return False

    member_statuses = (ChatMember.MEMBER, ChatMember.RESTRICTED, ChatMember.ADMINISTRATOR, ChatMember.OWNER)

    return chat_member_update.old_chat_member.status in member_statuses and chat_member_update.new_chat_member.status == ChatMember.LEFT


def is_kicked_update(chat_member_update: ChatMemberUpdated) -> bool:
    if chat_member_update.from_user.id == chat_member_update.new_chat_member.user.id:
        # performer of the action (chat_member_update.from_user) == user that changed status: user left (wasn't kicked)
        return False

    member_statuses = (ChatMember.MEMBER, ChatMember.RESTRICTED, ChatMember.ADMINISTRATOR, ChatMember.OWNER)

    return chat_member_update.old_chat_member.status in member_statuses and chat_member_update.new_chat_member.status == ChatMember.LEFT


def is_banned_update(chat_member_update: ChatMemberUpdated) -> bool:
    if chat_member_update.from_user.id == chat_member_update.new_chat_member.user.id:
        # performer of the action (chat_member_update.from_user) == user that changed status: user left (not kicked)
        return False

    member_statuses = (ChatMember.MEMBER, ChatMember.RESTRICTED, ChatMember.ADMINISTRATOR, ChatMember.OWNER)

    return chat_member_update.old_chat_member.status in member_statuses and chat_member_update.new_chat_member.status == ChatMember.BANNED


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

    return message.reply_to_message.forward_origin and isinstance(message.reply_to_message.forward_origin, MessageOriginChannel)


def detect_media_type(message: Message, raise_on_unknown_type=True) -> Optional[MessageType]:
    message_type = effective_message_type(message)

    if message_type == MessageType.PHOTO:
        return message_type
    elif message_type == MessageType.VIDEO:
        return message_type
    elif message_type == MessageType.ANIMATION:
        # must be before the 'document' check because message.document is also populated for gifs
        return message_type
    elif message_type == MessageType.DOCUMENT:
        return message_type
    elif message_type == MessageType.VOICE:
        return message_type
    elif message_type == MessageType.VIDEO_NOTE:
        return message_type
    elif message_type == MessageType.AUDIO:
        return message_type
    elif message_type == MessageType.STICKER:
        return message_type

    if raise_on_unknown_type:
        raise ValueError(f"message contains unknown media type or doesn't contain a media (MessageType: {message_type})")

    return


async def reply_media(message: Message, media_type: str, file_id: str, caption: Optional[str] = None, quote: Optional[bool] = None) -> Message:
    if media_type == MessageType.PHOTO:
        return await message.reply_photo(file_id, caption=caption, quote=quote)
    elif media_type == MessageType.VIDEO:
        return await message.reply_video(file_id, caption=caption, quote=quote)
    elif media_type == MessageType.DOCUMENT:
        return await message.reply_document(file_id, caption=caption, quote=quote)
    elif media_type == MessageType.VOICE:
        return await message.reply_voice(file_id, caption=caption, quote=quote)
    elif media_type == MessageType.VIDEO_NOTE:
        return await message.reply_video_note(file_id, quote=quote)
    elif media_type == MessageType.AUDIO:
        return await message.reply_audio(file_id, caption=caption, quote=quote)
    elif media_type == MessageType.ANIMATION:
        return await message.reply_animation(file_id, caption=caption, quote=quote)
    elif media_type == MessageType.STICKER:
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


def get_user_id_from_text(text: str, pattern: Optional[str] = None) -> Optional[int]:
    if not pattern:
        pattern = Regex.USER_ID_HASHTAG

    match = re.search(pattern, text, re.I)
    if not match:
        return

    return int(match.group("user_id"))


def generate_text_hash(text: str) -> str:
    # https://stackoverflow.com/a/3739928
    text_no_whitespaces = re.sub(r'(\s|\u180B|\u200B|\u200C|\u200D|\u2060|\uFEFF)+', '', text)
    md5_string = hashlib.md5(text_no_whitespaces.encode('utf-8')).hexdigest()

    return md5_string


def get_argument(text: str, commands: Optional[Union[List, str]] = None, bot_username="", remove_user_id_hashtag=False) -> str:
    prefixes = "".join(COMMAND_PREFIXES)

    if commands:
        if isinstance(commands, str):
            commands = [commands]

        for command in commands:
            text = re.sub(rf"^[{prefixes}]{command}(?:@{bot_username})?\s*", "", text, re.I)
    else:
        # remove any string that might be a command
        text = re.sub(rf"^[{prefixes}][\w_]+(?:@{bot_username})?\s*", "", text, re.I)

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
    return len(re.findall(r"(<(?:b|i|u|s|code|pre|blockquote(?: expandable)?)>|<a href=)", string))


def get_language_code(selected_language_code, telegram_language_code):
    if selected_language_code:
        return selected_language_code

    return telegram_language_code or Language.EN


async def delete_messages_safe(messages: Union[Message, List[Message]]) -> Optional[bool]:
    if not isinstance(messages, list):
        messages = [messages]

    success = False
    for message in messages:
        try:
            success = await message.delete()
        except BadRequest:
            pass

    if len(messages) == 1:
        return success


async def delete_or_remove_markup_by_ids_safe(bot: Bot, chat_id: int, message_id: int) -> (bool, bool):
    delete_success = False
    remove_markup_success = False

    try:
        delete_success = await bot.delete_message(chat_id, message_id)
    except BadRequest as e:
        logger.debug(f"error while deleting message {message_id} in chat {chat_id}: {e}")

    if not delete_success:
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
            remove_markup_success = True
        except BadRequest as e:
            if "not modified" in e.message.lower():
                remove_markup_success = True
            else:
                logger.debug(f"error while removing markup from message {message_id} in chat {chat_id}: {e}")

    return delete_success, remove_markup_success


async def delete_or_remove_markup_safe(message: Message) -> (bool, bool):
    delete_success = False
    remove_markup_success = False

    try:
        success = await message.delete()
    except BadRequest as e:
        logger.debug(f"error while deleting message {message.message_id} in chat {message.chat_id}: {e}")

    if not delete_success:
        try:
            await message.edit_reply_markup(reply_markup=None)
            remove_markup_success = True
        except BadRequest as e:
            if "not modified" in e.message.lower():
                remove_markup_success = True
            else:
                logger.debug(f"error while removing markup from message {message.message_id} in chat {message.chat_id}: {e}")

    return delete_success, remove_markup_success


async def delete_messages_by_id_safe(bot: Bot, chat_id: int, message_ids: Union[List[int], int]) -> Optional[Tuple[bool, str]]:
    """returns the request result if only one message_id was passed, otherwise None"""

    if not isinstance(message_ids, list):
        message_ids = [message_ids]

    success = None
    succes_description = "success"
    for message_id in message_ids:
        try:
            # delete_message will return true even when the message has already been deleted from the chat
            # (even by someone else)
            success = await bot.delete_message(chat_id, message_id)
        except BadRequest as e:
            logger.debug(f"error while deleting message {message_id} in chat {chat_id}: {e}")
            # if "message can't be deleted" in e.message.lower():
            success = False
            succes_description = e.message.lower()

    if len(message_ids) == 1:
        return success, succes_description


async def edit_text_safe(update: Update, *args, **kwargs):
    try:
        return await update.effective_message.edit_text(*args, **kwargs)
    except BadRequest as e:
        if "message is not modified" not in e.message.lower():
            raise e
        else:
            logger.info("message not modified exception ignored")


async def edit_text_by_ids_safe(
        bot: Bot,
        error_messages_to_ignore: Optional[List[str]] = None,
        *args,
        **kwargs
) -> Optional[Message]:
    if not error_messages_to_ignore:
        error_messages_to_ignore = ["message is not modified"]  # always ignore this exception

    try:
        return await bot.edit_message_text(*args, **kwargs)
    except BadRequest as e:
        error_message_lower = e.message.lower()
        exception_ignored = False

        for error_message in error_messages_to_ignore:
            if error_message.lower() in error_message_lower:
                exception_ignored = True
                logger.info(f"'{e.message}' exception ignored")
                break

        if not exception_ignored:
            raise e


async def remove_reply_markup_safe(bot: Bot, chat_id: int, message_id: int, raise_if_exception_is_not_message_not_modified=True):
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except BadRequest as e:
        if raise_if_exception_is_not_message_not_modified and "message is not modified" not in e.message.lower():
            raise e


async def pin_safe(message: Message, disable_notification=True) -> bool:
    try:
        return await message.pin(disable_notification=disable_notification)
    except (TelegramError, BadRequest, Forbidden) as e:
        logger.info(f"error while pinning: {e}")
        return False


async def unpin_safe(message: Message) -> bool:
    try:
        return await message.unpin()
    except (TelegramError, BadRequest, Forbidden) as e:
        logger.info(f"error while unpinning: {e}")
        return False


async def unpin_by_ids_safe(bot: Bot, chat_id: int, message_id: int) -> bool:
    try:
        return await bot.unpin_chat_message(chat_id, message_id)
    except (TelegramError, BadRequest, Forbidden) as e:
        logger.info(f"error while unpinning: {e}")
        return False


async def test_blocked(bot: Bot, user_id: int, raise_on_other_error: bool = True) -> Optional[bool]:
    try:
        await bot.send_chat_action(user_id, ChatAction.TYPING)
    except (TelegramError, BadRequest) as e:
        if e.message.lower() == "forbidden: bot was blocked by the user":
            # logger.warning("bot was blocked by the user")
            return True
        else:
            logger.warning(f"error while sending 'typing...' chat action: {e}")
            if raise_on_other_error:
                raise e

            return False


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
        year = year.lower().replace("k", "0")
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


def tme_link(chat_id: int, message_id: int, thread_id: Optional[int] = None):
    chat_id = re.sub(r"^-(?:100)?", "", str(chat_id))
    link = f"https://t.me/c/{chat_id}/{message_id}"

    if thread_id:
        link = f"{link}?thread={thread_id}"

    return link


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
    # past_dt = datetime.datetime(2023, 9, 28, 11 - 2, 30)
    # print(elapsed_str(past_dt))
    # print(elapsed_str_old(past_dt))
    # print(datetime.datetime(2023, 1, 1).isocalendar()[1])
    # print(week_start_end(datetime.date(2023, 10, 8)))
    # test = [10, 20, 30, 31, 60, 61, 122, 170]
    # for n in test:
    #     print(f"{n}: {round_to_hour(n)}")
    pass
