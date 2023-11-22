import json
import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext import filters

import decorators
import utilities
from constants import Group
from database.models import User, PrivateChatMessage

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_down_db_instances=True)
async def on_private_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.debug(f"saving new private chat message ({update.message.message_id}) {utilities.log(update)}")
    private_chat_message = PrivateChatMessage(
        message_id=update.message.message_id,
        user_id=update.effective_user.id,
        from_self=False,
        date=update.message.date,
        message_json=json.dumps(update.message.to_dict(), indent=2)
    )
    session.add(private_chat_message)


HANDLERS = (
    (MessageHandler(filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE, on_private_chat_message), Group.PREPROCESS),
)
