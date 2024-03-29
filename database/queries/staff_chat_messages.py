import datetime
import logging
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from telegram import Message

import utilities
from database.models import StaffChatMessage

logger = logging.getLogger(__name__)


class MinLength:
    TEXT = 60
    CAPTION = 60


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
    filters = [
        StaffChatMessage.chat_id == message.chat.id,
        StaffChatMessage.message_id != message.message_id,  # we already saved 'message' when the function is called
        # StaffChatMessage.text_hashing_version == HashingVersion.CURRENT
    ]

    if message.text and len(message.text) > MinLength.TEXT:
        text_hash = utilities.generate_text_hash(message.text)
        filters.append(StaffChatMessage.text_hash == text_hash)
    elif message.caption and len(message.caption) > MinLength.CAPTION and utilities.contains_media_with_file_id(message):
        _, media_file_unique_id, _ = utilities.get_media_ids(message)
        caption_text_hash = utilities.generate_text_hash(message.caption)

        filters.append(
            ((StaffChatMessage.media_file_unique_id == media_file_unique_id) | (StaffChatMessage.text_hash == caption_text_hash))
        )
    elif utilities.contains_media_with_file_id(message):
        # if no caption or caption is too chort, just check the file_unique_id
        _, media_file_unique_id, _ = utilities.get_media_ids(message)
        filters.append(StaffChatMessage.media_file_unique_id == media_file_unique_id)
    else:
        return []

    statement = select(StaffChatMessage).filter(*filters).order_by(StaffChatMessage.message_id.desc())

    return session.scalars(statement).all()


def select_old_messages(session: Session, older_than: datetime.datetime):
    statement = select(StaffChatMessage).filter(
        StaffChatMessage.message_date < older_than
    ).order_by(StaffChatMessage.message_id)

    return session.scalars(statement).all()


def delete_old_messages(session: Session, older_than: datetime.datetime):
    statement = delete(StaffChatMessage).where(StaffChatMessage.message_date < older_than)

    result = session.execute(statement)
    return result.rowcount
