from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update

from database.models import UserMessage


def get_user_message_by_id(session: Session, message_id: int) -> Optional[UserMessage]:
    user_message: UserMessage = session.query(UserMessage).filter(
        UserMessage.message_id == message_id
    ).one_or_none()

    return user_message


def get_user_message(session: Session, update: Update) -> Optional[UserMessage]:
    chat_id = update.effective_chat.id
    replied_to_message_id = update.message.reply_to_message.message_id

    user_message: UserMessage = session.query(UserMessage).filter(
        UserMessage.forwarded_chat_id == chat_id,
        UserMessage.forwarded_message_id == replied_to_message_id
    ).one_or_none()

    return user_message
