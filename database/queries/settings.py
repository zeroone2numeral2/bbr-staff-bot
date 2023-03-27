from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import true, false

from database.models import Setting, Chat
from constants import SettingKey, Language


def get_setting(
        session: Session,
        key: str,
        language: Optional[str] = None,
        chat_id: Optional[int] = None,
        create_if_missing=True
):
    filters = [
        Setting.key == key,
        Chat.default == true()
    ]
    if language:
        filters.append(Setting.language == language)

    setting: Setting = session.query(Setting).join(Chat).filter(*filters).one_or_none()

    if not setting and create_if_missing:
        if not chat_id:
            chat_id = session.query(Chat).filter(Chat.default == true()).one_or_none().chat_id

        setting = Setting(chat_id=chat_id, key=key, language=language)
        session.add(setting)

    return setting


def get_welcome(session: Session, language: Optional[str] = None):
    filters = [
        Setting.key == SettingKey.WELCOME,
        Chat.default == true()
    ]
    query = session.query(Setting).join(Chat).filter(
        *filters,
        Setting.language == language
    )
    setting: Setting = query.one_or_none()

    if not setting:
        # try to get the English version of the setting
        query = session.query(Setting).join(Chat).filter(
            *filters,
            Setting.language == Language.EN
        )
        setting: Setting = query.one_or_none()

    if not setting:
        raise ValueError(f"no {language}/en welcome setting for staff chat")

    return setting


def get_welcome_for_langauge(session: Session, language: str, create_if_missing=True, chat_id: Optional[int] = None):
    setting: Setting = session.query(Setting).join(Chat).filter(
        Setting.key == SettingKey.WELCOME,
        Setting.language == language,
        Chat.default == true()
    ).one_or_none()

    if not setting and create_if_missing:
        setting = Setting(chat_id=chat_id, key=SettingKey.WELCOME, language=language)
        session.add(setting)

    return setting
