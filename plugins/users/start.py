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
from constants import LANGUAGES, BotSettingKey, LocalizedTextKey, Group
from database.models import User
from database.queries import settings, texts
from replacements import replace_placeholders

logger = logging.getLogger(__name__)


def get_start_reply_markup(start_message_language: str, welcome_texts) -> Optional[InlineKeyboardMarkup]:
    keyboard = [[]]

    for welcome_text in welcome_texts:
        if welcome_text.language not in LANGUAGES:
            logger.debug(f"welcome text found for language {welcome_text.language}, but not available in LANGUAGES")
            continue
        if start_message_language != welcome_text.language:
            emoji = LANGUAGES[welcome_text.language]["emoji"]
            button = InlineKeyboardButton(emoji, callback_data=f"setlangstart:{welcome_text.language}")
            keyboard[0].append(button)

    if len(keyboard[0]) < 1:
        return

    return InlineKeyboardMarkup(keyboard)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_set_language_button_start(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"set language button (from /start) {utilities.log(update)}")
    selected_language = context.matches[0].group(1)
    user.selected_language = selected_language

    await update.callback_query.answer(f"language set to {LANGUAGES[user.selected_language]['emoji']}", show_alert=False)

    language_code = utilities.get_language_code(user.selected_language, update.effective_user.language_code)

    welcome_text = texts.get_localized_text(session, LocalizedTextKey.WELCOME, language_code)
    welcome_texts = texts.get_texts(session, LocalizedTextKey.WELCOME).all()
    reply_markup = get_start_reply_markup(language_code, welcome_texts)

    text = replace_placeholders(welcome_text.value, update.effective_user, session)

    await update.effective_message.edit_text(text, reply_markup=reply_markup)

    user.set_started()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None,
                           user: Optional[User] = None):
    logger.info(f"/start {utilities.log(update)}")

    language_code = utilities.get_language_code(user.selected_language, update.effective_user.language_code)

    welcome_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.WELCOME,
        language_code,
        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    )
    welcome_texts = texts.get_texts(session, LocalizedTextKey.WELCOME).all()
    reply_markup = get_start_reply_markup(welcome_text.language, welcome_texts)

    text = replace_placeholders(welcome_text.value, update.effective_user, session)
    await update.message.reply_text(text, reply_markup=reply_markup)

    user.set_started()


HANDLERS = (
    (CommandHandler('start', on_start_command, filters.ChatType.PRIVATE), Group.NORMAL),
    (CallbackQueryHandler(on_set_language_button_start, pattern="^setlangstart:(..)$"), Group.NORMAL),
)
