from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update

from database.models import AdminMessage


def get_admin_message(session: Session, update: Update) -> Optional[AdminMessage]:
    chat_id = update.effective_chat.id
    message_id = update.message.reply_to_message.message_id

    admin_message: AdminMessage = session.query(AdminMessage).filter(
        AdminMessage.chat_id == chat_id,
        AdminMessage.message_id == message_id
    ).one_or_none()

    return admin_message
