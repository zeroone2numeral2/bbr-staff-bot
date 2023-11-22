import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.error import TelegramError, BadRequest
from telegram.ext import ContextTypes, filters, MessageHandler

import decorators
import utilities
from constants import BotSettingKey, Group
from database.models import Chat, AdminMessage
from database.queries import settings
from ext.filters import ChatFilter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_edited_message_staff(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"message edit in a group {utilities.log(update)}")
    if not settings.get_or_create(session, BotSettingKey.BROADCAST_EDITS).value():
        logger.info("message edits are disabled")
        return

    admin_message: AdminMessage = session.query(AdminMessage).filter(
        AdminMessage.chat_id == update.effective_chat.id,
        AdminMessage.message_id == update.effective_message.message_id
    ).one_or_none()
    if not admin_message:
        logger.info(f"couldn't find edited message in the db")
        return

    logger.info(f"editing message {admin_message.reply_message_id} in chat {admin_message.user_message.user_id}")
    try:
        new_message = await context.bot.edit_message_text(
            chat_id=admin_message.user_message.user_id,
            message_id=admin_message.reply_message_id,
            text=update.effective_message.text_html
        )
        admin_message.save_message_json(new_message)
    except (TelegramError, BadRequest) as e:
        logger.error(f"error while editing staff message in users chat: {e}")


HANDLERS = (
    (MessageHandler(ChatFilter.STAFF & filters.UpdateType.EDITED_MESSAGE & filters.TEXT, on_edited_message_staff), Group.PREPROCESS),
)
