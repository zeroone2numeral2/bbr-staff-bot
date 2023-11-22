from typing import Optional, Union, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import BotSetting


def get_settings(session: Session):
    statement = select(BotSetting).where()
    return session.scalars(statement)


def get_settings_as_dict(
        session: Session,
        include_categories: Optional[Union[List[str], str]] = None,
        exclude_categories: Optional[Union[List[str], str]] = None
):
    filters = []
    if include_categories:
        if isinstance(include_categories, str):
            include_categories = [include_categories]
        filters.append(BotSetting.category.in_(include_categories))
    if exclude_categories:
        if isinstance(exclude_categories, str):
            exclude_categories = [exclude_categories]
        filters.append(BotSetting.category.not_in(exclude_categories))

    statement = select(BotSetting).filter(*filters)
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
