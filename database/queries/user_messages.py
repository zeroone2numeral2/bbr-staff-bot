from typing import Optional, List, Tuple, Union

from sqlalchemy import true, false
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from telegram import ChatMemberAdministrator, ChatMemberOwner, Message, Update

from database.models import UserMessage, Chat, ChatAdministrator, chat_members_to_dict
from constants import SettingKey, Language


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
