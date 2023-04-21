from typing import Optional, List, Tuple, Union

from sqlalchemy import true, false, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from telegram import Message, Update

from database.models import PrivateChatMessage, User
from constants import Language


def get_messages(session: Session, user_id: int):
    statement = select(PrivateChatMessage).where(
        PrivateChatMessage.user_id == user_id,
        PrivateChatMessage.revoked == false()
    )

    return session.scalars(statement)


def save(session: Session, message: Union[Message, Update], commit: Optional[bool] = False):
    if isinstance(message, Update):
        message = message.effective_message

    if message.chat.id < 0:
        raise ValueError("cannot save PrivateChatMessage for non-private chat")

    private_chat_message = PrivateChatMessage(message.message_id, message.chat.id, message.to_json())
    session.add(private_chat_message)
    if commit:
        session.commit()
