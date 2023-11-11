import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, User as TelegramUser, Message
from telegram.ext import ContextTypes

import utilities
from database.models import Chat, User, UserMessage
from database.queries import chat_members, user_messages, users

logger = logging.getLogger(__name__)


def can_evaluate_applications(session: Session, user: TelegramUser):
    if utilities.is_superadmin(user):
        return True

    chat_member = chat_members.get_chat_member(session, user.id, Chat.is_evaluation_chat)
    if chat_member:
        return chat_member.is_administrator()

    return False


async def get_user_instance_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session) -> Optional[User]:
    message: Message = update.message

    # first: try to get the user object from a forwarded message from the user to the staff
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        user_message: UserMessage = user_messages.get_user_message(session, update)
        if user_message:
            user: User = user_message.user
            return user
        else:
            logger.info(f"couldn't find replied-to message in the database, message_id: {message.reply_to_message.message_id}")

    # the: try to get it from the message text
    user_id = utilities.get_user_id_from_text(message.text)

    # if still no user_id, look for it in the replied-to message text/caption
    if not user_id and message.reply_to_message and (message.reply_to_message.text or message.reply_to_message.caption):
        # try to search the hashtag in the replied-to message
        text = message.reply_to_message.text or message.reply_to_message.caption
        user_id = utilities.get_user_id_from_text(text)

    if not user_id:
        logger.info("can't find user id in text/replied-to message's text")
        await update.message.reply_text(
            "<i>can't detect the user's ID\nreply to one of their forwarded messages or to a message containing their #id1234567 hasthag, "
            "or include the ID hashtag after the command</i>",
            quote=True
        )
        return

    user: User = users.get_or_create(session, user_id, create_if_missing=False)
    if not user:
        logger.info(f"can't find user {user_id} in the database")
        await update.message.reply_text(f"can't find user <code>{user_id}</code> in the database", quote=True)
        return

    return user
