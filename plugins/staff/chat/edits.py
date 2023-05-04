import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, filters, MessageHandler

from database.models import Chat, AdminMessage
from database.queries import settings
import decorators
import utilities
from constants import BotSettingKey, Group

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_edited_message_staff(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"message edit in a group {utilities.log(update)}")
    if not settings.get_or_create(session, BotSettingKey.BROADCAST_EDITS).value():
        logger.info("message edits are disabled")
        return

    if not chat.is_staff_chat:
        logger.info(f"ignoring edited message update: chat is not the current staff chat")
        return

    admin_message: AdminMessage = session.query(AdminMessage).filter(
        AdminMessage.chat_id == update.effective_chat.id,
        AdminMessage.message_id == update.effective_message.message_id
    ).one_or_none()
    if not admin_message:
        logger.info(f"couldn't find edited message in the db")
        return

    logger.info(f"editing message {admin_message.reply_message_id} in chat {admin_message.user_message.user_id}")
    await context.bot.edit_message_text(
        chat_id=admin_message.user_message.user_id,
        message_id=admin_message.reply_message_id,
        text=update.effective_message.text_html
    )


HANDLERS = (
    (MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT & filters.ChatType.GROUPS, on_edited_message_staff), Group.PREPROCESS),
)
