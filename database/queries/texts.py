from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import true, false, select, null

from database.models import LocalizedText
from constants import LocalizedTextKey, Language


def get_localized_text(
        session: Session,
        key: str,
        language: str,
        create_if_missing=True
):
    text: LocalizedText = session.query(LocalizedText).filter(
        LocalizedText.key == key,
        LocalizedText.language == language
    ).one_or_none()

    if not text and create_if_missing:
        text = LocalizedText(key=key, language=language)
        session.add(text)

    return text


def get_localized_text_with_fallback(
        session: Session,
        key: str,
        language: str,
        fallback_language: Optional[str] = Language.EN,
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
        raise ValueError(f"no {language}/en <{key}> text")

    return text


def get_texts(session: Session, key: str):
    statement = select(LocalizedText).where(LocalizedText.key == key)
    return session.execute(statement)


def get_or_create_localized_text(session: Session, key: str, language: str, create_if_missing=True):
    text: LocalizedText = session.query(LocalizedText).filter(
        LocalizedText.key == key,
        LocalizedText.language == language
    ).one_or_none()

    if not text and create_if_missing:
        text = LocalizedText(key=key, language=language)
        session.add(text)

    return text
