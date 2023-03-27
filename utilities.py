import json
import logging
import logging.config
import re
from html import escape
from typing import Union
from typing import List

from telegram import User

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
