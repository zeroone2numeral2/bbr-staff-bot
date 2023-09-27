import json
import logging
from typing import Optional, List, Union

from sqlalchemy import false, select
from sqlalchemy.orm import Session
from telegram import Message, Update

import utilities
from database.models import StaffChatMessage

logger = logging.getLogger(__name__)


def get_or_create(session: Session, message: Message, create_if_missing=True, commit=False) -> Optional[StaffChatMessage]:
    staff_chat_message: StaffChatMessage = session.query(StaffChatMessage).filter(
        StaffChatMessage.chat_id == message.chat.id,
        StaffChatMessage.message_id == message.message_id
    ).one_or_none()

    if not staff_chat_message and create_if_missing:
        staff_chat_message = StaffChatMessage(message)
        session.add(staff_chat_message)
        if commit:
            session.commit()

    return staff_chat_message


def find_duplicates(session: Session, message: Message):
    filters = list()
    filters.append(StaffChatMessage.chat_id == message.chat.id)
    filters.append(StaffChatMessage.message_id != message.message_id)  # we already saved this message

    if message.text:
        text_hash = utilities.generate_text_hash(message.text)
        filters.append(StaffChatMessage.text_hash == text_hash)
    elif utilities.contains_media_with_file_id(message):
        _, media_file_unique_id, _ = utilities.get_media_ids(message)
        filters.append(StaffChatMessage.media_file_unique_id == media_file_unique_id)
    else:
        return []

    statement = select(StaffChatMessage).filter(*filters).order_by(StaffChatMessage.message_id.desc())

    return session.scalars(statement).all()