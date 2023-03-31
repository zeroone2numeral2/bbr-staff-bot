from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import true, false, select, null
from telegram import User as TelegramUser

from database.models import User


def get_or_create(session: Session, user_id: int, create_if_missing=True, telegram_user: Optional[TelegramUser] = None):
    user: User = session.query(User).filter(User.user_id == user_id).one_or_none()

    if not user and create_if_missing:
        user = User(telegram_user)
        user.add(user)

    return user
