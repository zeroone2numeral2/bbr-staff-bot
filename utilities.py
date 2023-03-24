import json
import logging
import logging.config
from html import escape

from telegram import User

from config import config


def load_logging_config(file_name='logging.json'):
    with open(file_name, 'r') as f:
        logging_config = json.load(f)

    logging.config.dictConfig(logging_config)


def escape_html(string):
    return escape(str(string))


def is_admin(user: User) -> bool:
    return user.id in config.telegram.admins

