from typing import Optional, List

from sqlalchemy import select, false, and_
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


def get_events(
        session: Session,
        chat_id: Optional[int] = None,
        skip_canceled: bool = False,
        filters: Optional[List] = None,
        order_by_type=False
):
    if not filters:
        filters = []

    filters.append(Event.deleted == false())

    if chat_id:
        filters.append(Event.chat_id == chat_id)
    if skip_canceled:
        filters.append(Event.canceled == false())

    order_by_default = [
        Event.start_year,
        Event.start_month,
        Event.start_day,
        Event.message_id
    ]

    if order_by_type:
        order_by = [Event.event_type, Event.region]
        order_by.extend(order_by_default)
    else:
        order_by = order_by_default

    query = select(Event).filter(*filters).order_by(*order_by)

    return session.scalars(query)


def get_all_events(session: Session):
    statement = select(Event).where().order_by(
        Event.start_year,
        Event.start_month,
        Event.start_day,
        Event.message_id
    )

    return session.scalars(statement)
