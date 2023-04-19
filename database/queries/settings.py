from sqlalchemy.orm import Session
from sqlalchemy import select

from database.models import BotSetting


def get_settings(session: Session):
    statement = select(BotSetting).where()
    return session.scalars(statement)


def get_settings_as_dict(session: Session):
    statement = select(BotSetting).where()
    settings_dict = {}
    for setting in session.scalars(statement):
        settings_dict[setting.key] = setting
    return settings_dict


def get_or_create(session: Session, key: str, create_if_missing=True, value=None):
    setting: BotSetting = session.query(BotSetting).filter(BotSetting.key == key).one_or_none()

    if not setting and create_if_missing:
        setting = BotSetting(key=key, value=value)
        session.add(setting)

    return setting
