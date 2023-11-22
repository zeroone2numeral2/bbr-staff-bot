import logging

from sqlalchemy.orm import Session
from telegram import User as TelegramUser

import utilities
from database.models import Chat
from database.queries import chat_members

logger = logging.getLogger(__name__)


def can_evaluate_applications(session: Session, user: TelegramUser):
    if utilities.is_superadmin(user):
        return True

    chat_member = chat_members.get_chat_member(session, user.id, Chat.is_evaluation_chat)
    if chat_member:
        return chat_member.is_administrator()

    return False
