import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext import filters

from database.models import User, PrivateChatMessage
import decorators
import utilities
from constants import Group

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_down_db_instances=True)
async def on_private_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"saving new private chat message {utilities.log(update)}")
    private_chat_message = PrivateChatMessage(update.message.message_id, update.effective_user.id, update.message.to_json())
    session.add(private_chat_message)


HANDLERS = (
    (MessageHandler(filters.ChatType.PRIVATE, on_private_chat_message), Group.PREPROCESS),
)
