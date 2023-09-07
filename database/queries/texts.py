from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import LocalizedText


def get_localized_text(
        session: Session,
        key: str,
        language: str,
        create_if_missing=True,
        show_if_true_bot_setting_key: Optional[str] = None
):
    text: LocalizedText = session.query(LocalizedText).filter(
        LocalizedText.key == key,
        LocalizedText.language == language
    ).one_or_none()

    if not text and create_if_missing:
        text = LocalizedText(key=key, language=language, show_if_true_bot_setting_key=show_if_true_bot_setting_key)
        session.add(text)

    return text


def get_localized_text_with_fallback(
        session: Session,
        key: str,
        language: str,
        fallback_language: str,
        raise_if_no_fallback: Optional[bool] = True
):
    query = session.query(LocalizedText).filter(
        LocalizedText.key == key,
        LocalizedText.language == language
    )
    text: LocalizedText = query.one_or_none()

    if not text:
        # try to get the fallback (English) version of the setting
        query = session.query(LocalizedText).filter(
            LocalizedText.key == key,
            LocalizedText.language == fallback_language
        )
        text: LocalizedText = query.one_or_none()

    if not text and raise_if_no_fallback:
        raise ValueError(f"no {language}/{fallback_language} <{key}> text")

    return text


def get_texts(session: Session, key: str):
    statement = select(LocalizedText).where(LocalizedText.key == key)
    return session.scalars(statement)


def get_texts_as_dict(session: Session):
    statement = select(LocalizedText).where()
    texts_dict = {}
    for ltext in session.scalars(statement):
        texts_dict[ltext.key] = ltext
    return texts_dict


def get_or_create_localized_text(session: Session, key: str, language: str, create_if_missing=True, value: Optional[str] = None):
    text: LocalizedText = session.query(LocalizedText).filter(
        LocalizedText.key == key,
        LocalizedText.language == language
    ).one_or_none()

    if not text and create_if_missing:
        text = LocalizedText(key=key, language=language, value=value)
        session.add(text)

    return text
