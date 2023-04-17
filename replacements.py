from typing import Optional

from sqlalchemy.orm import Session
from telegram import User as TelegramUser
from telegram import helpers

import utilities
from constants import LANGUAGES, Language, BotSettingKey
from database.queries import settings

PLACEHOLDER_REPLACEMENTS_TELEGRAM_USER = {
    "{NAME}": lambda u: utilities.escape_html(u.first_name),
    "{SURNAME}": lambda u: utilities.escape_html(u.last_name),
    "{FULLNAME}": lambda u: utilities.escape_html(u.full_name),
    "{USERNAME}": lambda u: f"@{u.username}" if u.username else "-",
    "{MENTION}": lambda u: helpers.mention_html(u.id, utilities.escape_html(u.first_name)),
    "{LANG}": lambda u: LANGUAGES[u.language_code]["desc"] if u.language_code else LANGUAGES[Language.EN]["desc"],
    "{LANGEMOJI}": lambda u: LANGUAGES[u.language_code]["emoji"] if u.language_code else LANGUAGES[Language.EN]["emoji"]
}


PLACEHOLDER_REPLACEMENTS_DATABASE = {
    "{CHATLINK}": lambda s: settings.get_or_create(s, BotSettingKey.CHAT_INVITE_LINK).value(),
}


def replace_placeholders(text: str, user: Optional[TelegramUser] = None, session: Optional[Session] = None):
    if user:
        for placeholder, repl_func in PLACEHOLDER_REPLACEMENTS_TELEGRAM_USER.items():
            text = text.replace(placeholder, repl_func(user))

    if session is not None:
        for placeholder, repl_func in PLACEHOLDER_REPLACEMENTS_DATABASE.items():
            text = text.replace(placeholder, repl_func(session))

    return text
