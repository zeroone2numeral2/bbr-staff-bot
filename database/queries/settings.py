from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import true, false, select

from database.models import Setting, Chat
from constants import SettingKey, Language


def get_setting(
        session: Session,
        key: str,
        language: Optional[str] = None,
        create_if_missing=True
):
    filters = [
        Setting.key == key
    ]
    if language:
        filters.append(Setting.language == language)

    setting: Setting = session.query(Setting).filter(*filters).one_or_none()

    if not setting and create_if_missing:
        setting = Setting(key=key, language=language)
        session.add(setting)

    return setting


def get_localized_setting(
        session: Session,
        key: str,
        language: str,
        fallback_language: Optional[str] = Language.EN,
        raise_if_no_fallback: Optional[bool] = True
):
    filters = [Setting.key == key]
    query = session.query(Setting).filter(
        *filters,
        Setting.language == language
    )
    setting: Setting = query.one_or_none()

    if not setting:
        # try to get the fallback (English) version of the setting
        query = session.query(Setting).filter(
            *filters,
            Setting.language == fallback_language
        )
        setting: Setting = query.one_or_none()

    if not setting and raise_if_no_fallback:
        raise ValueError(f"no {language}/en <{key}> setting")

    return setting


def get_settings(session: Session, key: str):
    statement = select(Setting).where(Setting.key == key)
    return session.execute(statement)


def get_or_create_localized_setting(session: Session, key: str, language: str, create_if_missing=True):
    setting: Setting = session.query(Setting).filter(
        Setting.key == key,
        Setting.language == language
    ).one_or_none()

    if not setting and create_if_missing:
        setting = Setting(key=key, language=language)
        session.add(setting)

    return setting


def get_or_create_setting(session: Session, key: str, create_if_missing=True):
    setting: Setting = session.query(Setting).filter(
        Setting.key == key
    ).one_or_none()

    if not setting and create_if_missing:
        setting = Setting(key=key)
        session.add(setting)

    return setting
