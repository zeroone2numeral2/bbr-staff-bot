import json
import logging
from typing import Optional, List, Union

from sqlalchemy import false, select
from sqlalchemy.orm import Session
from telegram import Message, Update

from database.models import PrivateChatMessage

logger = logging.getLogger(__name__)


def get_messages(session: Session, user_id: int):
    statement = select(PrivateChatMessage).where(
        PrivateChatMessage.user_id == user_id,
        PrivateChatMessage.revoked == false()
    ).order_by(PrivateChatMessage.message_id)

    return session.scalars(statement)


def save(session: Session, messages: [Union[Message, Update], List[Union[Message, Update]]], commit: Optional[bool] = False):
    if not isinstance(messages, List):
        messages = [messages]

    new_instances = []
    for message in messages:
        if isinstance(message, Update):
            message = message.effective_message

        message: Message
        if message.chat.id < 0:
            raise ValueError("cannot save PrivateChatMessage for non-private chat")

        # logger.debug(f"saving message_id {message.message_id}")
        private_chat_message = PrivateChatMessage(
            message_id=message.message_id,
            user_id=message.chat.id,
            from_self=message.from_user.is_bot,
            date=message.date,
            message_json=json.dumps(message.to_dict(), indent=2)
        )
        new_instances.append(private_chat_message)

    # see https://stackoverflow.com/a/69488288
    session.add_all(new_instances)
    if commit:
        session.commit()
