import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.ext import CommandHandler
from telegram.ext import filters

from database.models import User, ChatMember as DbChatMember
from database.queries import settings, texts, chat_members, chats
import decorators
import utilities
from replacements import replace_placeholders
from constants import LANGUAGES, BotSettingKey, LocalizedTextKey, Group, Language

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/start {utilities.log(update)}")

    chat_member = chat_members.get_users_chat_chat_member(session, update.effective_user.id)
    if not chat_member:
        users_chat = chats.get_users_chat(session)
        logger.info(f"no record for user {update.effective_user.id} in chat {users_chat.chat_id}, fetching ChatMember...")
        tg_chat_member = await context.bot.get_chat_member(users_chat.chat_id, update.effective_user.id)
        chat_member = DbChatMember.from_chat_member(users_chat.chat_id, tg_chat_member)
        session.add(chat_member)
        session.commit()

    if chat_member.is_member():
        logger.info("user is already a member of the users chat")
        await update.message.reply_text("sei già membro del gruppo :)")
    else:
        welcome_text = texts.get_localized_text_with_fallback(
            session,
            LocalizedTextKey.WELCOME,
            Language.IT,
            fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
        )

        text = replace_placeholders(welcome_text.value, update.effective_user, session)
        await update.message.reply_text(text)

    user.set_started()


HANDLERS = (
    (CommandHandler('start', on_start_command, filters.ChatType.PRIVATE), Group.NORMAL),
)
