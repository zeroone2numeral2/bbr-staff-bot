import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram import Update
from telegram.ext import CommandHandler
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.ext import filters

import decorators
import utilities
from constants import LANGUAGES, Group
from database.models import User

logger = logging.getLogger(__name__)


def get_all_languages_reply_markup(user_language: str) -> InlineKeyboardMarkup:
    keyboard = [[]]

    for language_code, language_data in LANGUAGES.items():
        if user_language != language_code:
            button = InlineKeyboardButton(language_data["emoji"], callback_data=f"setlang:{language_code}")
            keyboard[0].append(button)

    return InlineKeyboardMarkup(keyboard)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_set_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"set language button {utilities.log(update)}")
    selected_language = context.matches[0].group(1)
    user.selected_language = selected_language

    await update.callback_query.edit_message_text(
        f"Your language has been set to {LANGUAGES[user.selected_language]['emoji']}\nUse the buttons below to change language:",
        reply_markup=get_all_languages_reply_markup(selected_language)
    )



@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"/lang {utilities.log(update)}")

    language_code = utilities.get_language_code(user.selected_language, update.effective_user.language_code)
    reply_markup = get_all_languages_reply_markup(language_code)

    text = f"Your current language is {LANGUAGES[language_code]['emoji']}\nUse the buttons below to change language:"
    await update.effective_message.reply_text(text, reply_markup=reply_markup)


HANDLERS = (
    (CommandHandler('lang', on_lang_command, filters.ChatType.PRIVATE), Group.NORMAL),
    (CallbackQueryHandler(on_set_language_button, pattern="^setlang:(..)$"), Group.NORMAL),
)
