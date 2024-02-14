import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, Message
from telegram.ext import ContextTypes

import utilities
from database.models import User, UserMessage
from database.queries import user_messages, users

logger = logging.getLogger(__name__)


async def get_user_instance_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session) -> Optional[User]:
    message: Message = update.message

    # first: try to get it from the message text
    user_id = utilities.get_user_id_from_text(message.text)

    # if no user_id, look for it in the replied-to message text/caption
    if not user_id and message.reply_to_message and (message.reply_to_message.text or message.reply_to_message.caption):
        # try to search the hashtag in the replied-to message
        text = message.reply_to_message.text or message.reply_to_message.caption
        user_id = utilities.get_user_id_from_text(text)

    # if still no user_id, check whether the message is a reply to a bot-forwarded message from the user
    if not user_id and message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        user_message: UserMessage = user_messages.get_user_message(session, update)
        if user_message:
            user_id = user_message.user.user_id

    if not user_id:
        logger.info("can't find user id in text/replied-to message's text/not an user's forwarded message")
        await update.message.reply_text(
            "<i>can't detect the user's ID\nreply to one of their forwarded messages or to a message containing their #id1234567 hasthag, "
            "or include the ID hashtag after the command</i>",
            do_quote=True
        )
        return
    else:
        logger.info(f"user_id found: {user_id}")
        user: Optional[User] = users.get_or_create(session, user_id, create_if_missing=False)
        if not user:
            logger.info(f"can't find user in the database")
            await update.message.reply_text(f"can't find user <code>{user_id}</code> in the database", do_quote=True)
            return

    return user
