from typing import Optional

from sqlalchemy import select, false
from sqlalchemy.orm import Session

import utilities
from database.models import Event


def get_or_create(session: Session, chat_id: int, message_id: int, create_if_missing=True, commit=False) -> Optional[Event]:
    event: Event = session.query(Event).filter(Event.chat_id == chat_id, Event.message_id == message_id).one_or_none()

    if not event and create_if_missing:
        event = Event(chat_id, message_id)
        session.add(event)
        if commit:
            session.commit()

    return event


def get_events(session: Session, chat_id: int):
    now = utilities.now()
    statement = select(Event).where(
        Event.chat_id == chat_id,
        Event.canceled == false(),
        Event.start_year >= now.year,
        Event.start_month >= now.month,
        # select any event in the current month
    ).order_by(
        Event.start_year,
        Event.start_month,
        Event.start_day,
        Event.message_id
    )

    return session.scalars(statement)
