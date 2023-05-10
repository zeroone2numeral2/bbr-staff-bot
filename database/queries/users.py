from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import true, false, select, null
from telegram import User as TelegramUser

from database.models import User


def get_or_create(session: Session, user_id: int, create_if_missing=True, telegram_user: Optional[TelegramUser] = None):
    user: User = session.query(User).filter(User.user_id == user_id).one_or_none()

    if not user and create_if_missing:
        user = User(telegram_user)
        session.add(user)

    return user


def get_safe(session: Session, telegram_user: TelegramUser, create_if_missing=True, update_metadata_if_existing=True, commit=False):
    user: User = session.query(User).filter(User.user_id == telegram_user.id).one_or_none()

    if not user and create_if_missing:
        user = User(telegram_user)
        session.add(user)
    elif user and update_metadata_if_existing:
        user.update_metadata(telegram_user)

    if commit:
        session.commit()

    return user
