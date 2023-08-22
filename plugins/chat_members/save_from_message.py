import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import MessageHandler, filters, ContextTypes

from constants import Group
from database.models import User, Chat, ChatMember as DbChatMember
from database.queries import chat_members
import decorators
import utilities
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User, chat: Chat):
    if not config.settings.save_chat_member_from_message:
        return

    if not (chat.is_users_chat or chat.is_staff_chat or chat.is_evaluation_chat):
        # don't do anything if not one of these groups
        return

    logger.debug(f"group message: saving chat member {utilities.log(update)}")
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    db_chat_member = chat_members.get_chat_chat_member(session, user_id, chat_id)
    if db_chat_member:
        # chat member records exist: do nothing
        return

    logger.info("saving previously unknown chat member...")
    try:
        tg_chat_member = await update.effective_chat.get_member(user_id)
    except (BadRequest, TelegramError) as e:
        logger.warning(f"error while getting chat member from telegram: {e}")
        return

    db_chat_member = DbChatMember.from_chat_member(chat_id, tg_chat_member)
    session.add(db_chat_member)


HANDLERS = (
    (MessageHandler(filters.ChatType.GROUPS & ~filters.SenderChat.ALL, on_group_message), Group.POSTPROCESS),
)

