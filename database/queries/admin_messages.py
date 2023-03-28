from typing import Optional, List, Tuple, Union

from sqlalchemy import true, false
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from telegram import ChatMemberAdministrator, ChatMemberOwner, Message, Update

from database.models import UserMessage, Chat, ChatAdministrator, AdminMessage
from constants import SettingKey, Language


def get_admin_message(session: Session, update: Update) -> Optional[AdminMessage]:
    chat_id = update.effective_chat.id
    message_id = update.message.reply_to_message.message_id

    admin_message: AdminMessage = session.query(AdminMessage).filter(
        AdminMessage.chat_id == chat_id,
        AdminMessage.message_id == message_id
    ).one_or_none()

    return admin_message
