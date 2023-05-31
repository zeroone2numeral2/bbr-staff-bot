import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import MessageHandler, filters, ContextTypes

import decorators
import utilities
from constants import Group
from database.models import User, UserMessage
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_edited_message_user(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.error("user-sent messages cannot be edited because they are forwarded")

    logger.info(f"message edit in a private chat {utilities.log(update)}")
    if not config.settings.broadcast_message_edits:
        return

    user_message: UserMessage = session.query(UserMessage).filter(
        UserMessage.message_id == update.effective_message.message_id
    ).one_or_none()
    if not user_message:
        logger.info(f"couldn't find edited message in the db")
        return

    logger.info(f"editing message {user_message.forwarded_message_id} in chat {user_message.forwarded_chat_id}")
    await context.bot.edit_message_text(
        chat_id=user_message.forwarded_chat_id,
        message_id=user_message.forwarded_message_id,
        text=update.effective_message.text_html
    )


HANDLERS = (
    (MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT & filters.ChatType.PRIVATE, on_edited_message_user), Group.NORMAL),
)
