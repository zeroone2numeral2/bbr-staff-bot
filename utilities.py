import json
import logging
import logging.config
import re
from html import escape
from typing import Union
from typing import List

from telegram import User, Update, Chat
from telegram.error import BadRequest

from config import config
from constants import COMMAND_PREFIXES


def load_logging_config(file_name='logging.json'):
    with open(file_name, 'r') as f:
        logging_config = json.load(f)

    logging.config.dictConfig(logging_config)


def escape_html(string):
    return escape(str(string))


def is_admin(user: User) -> bool:
    return user.id in config.telegram.admins


def get_argument(commands: Union[List, str], text: str) -> str:
    if isinstance(commands, str):
        commands = [commands]

    prefixes = "".join(COMMAND_PREFIXES)

    for command in commands:
        text = re.sub(rf"^[{prefixes}]{command}\s*", "", text, re.I)

    return text.strip()


async def edit_text_safe(update: Update, *args, **kwargs):
    try:
        await update.effective_message.edit_text(*args, **kwargs)
    except BadRequest as e:
        if "message is not modified" not in e.message.lower():
            raise e


def user_log(user: User):
    return f"{user.id} ({user.full_name} [{user.language_code}])"


def chat_log(chat: Chat):
    return f"{chat.id} ({chat.title})"


def log_old(obj: Union[User, Chat]):
    if isinstance(obj, User):
        return user_log(obj)
    elif isinstance(obj, Chat):
        return chat_log(obj)


def log(update: Update):
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
