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

    # send the rabbit message then delete (it will be less noticeable that messages are being deleted)
    sent_message = await update.message.reply_photo("AgACAgQAAxkBAAIF4WRCV9_H-H1tQHnA2443fXtcVy4iAAKkujEbkmDgUYIhRK-rWlZHAQADAgADeAADLwQ")

    messages: List[PrivateChatMessage] = private_chat_messages.get_messages(session, update.effective_user.id)
    for message in messages:
        logger.debug(f"deleting message {message.message_id} from chat {update.effective_user.id}")
        await context.bot.delete_message(update.effective_user.id, message.message_id)
        message.set_revoked(reason="/delhistory command")

    private_chat_messages.save(session, sent_message)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_fileid_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/fileid {utilities.log(update)}")

    print(update.message.reply_to_message.photo[-1].file_id)


HANDLERS = (
    (MessageHandler(filters.ChatType.PRIVATE & filters.UpdateType.MESSAGE, on_private_chat_message), Group.PREPROCESS),
    (CommandHandler(["delhistory"], on_test_delhistory), Group.NORMAL),
    (CommandHandler(["fileid"], on_fileid_command), Group.NORMAL),
)
