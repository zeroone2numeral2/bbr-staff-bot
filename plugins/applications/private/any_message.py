import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, CommandHandler
from telegram.ext import filters

from database.models import User, PrivateChatMessage
import decorators
import utilities
from constants import Group
from database.queries import private_chat_messages

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_down_db_instances=True)
async def on_private_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"saving new private chat message ({update.message.message_id}) {utilities.log(update)}")
    private_chat_message = PrivateChatMessage(
        message_id=update.message.message_id,
        user_id=update.effective_user.id,
        from_self=False,
        message_json=update.message.to_json()
    )
    session.add(private_chat_message)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_test_delhistory(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/delhistory {utilities.log(update)}")

    messages: List[PrivateChatMessage] = private_chat_messages.get_messages(session, update.effective_user.id)
    for message in messages:
        logger.debug(f"deleting message {message.message_id} from chat {update.effective_user.id}")
        await context.bot.delete_message(update.effective_user.id, message.message_id)
        message.revoke("/delhistory command")


HANDLERS = (
    (MessageHandler(filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE, on_private_chat_message), Group.PREPROCESS),
    (CommandHandler(["delhistory"], on_test_delhistory), Group.NORMAL),
)