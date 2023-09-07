import datetime
from typing import Optional, List, Any, Tuple

from sqlalchemy import select, false, null
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
        order_by_type=False,
        order_by_override: Optional[List] = None  # list of Event class property to use as order_by
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
        Event.region,
        Event.message_id
    ]

    if order_by_type:
        order_by = [Event.event_type, Event.region]
        order_by.extend(order_by_default)
    elif order_by_override:
        order_by = order_by_override
    else:
        order_by = order_by_default

    query = select(Event).filter(*filters).order_by(*order_by)

    return session.scalars(query)


def get_week_events(session: Session, now: datetime.datetime, filters: List) -> Tuple[Any, datetime.datetime, datetime.datetime]:
    last_monday = utilities.previous_weekday(today=now.date(), weekday=0)
    next_monday = utilities.next_weekday(today=now.date(), weekday=0)

    filters.extend([
        # start date is between last monday and next monday...
        (
            (Event.start_date >= last_monday)
            & (Event.start_date < next_monday)
        )
        # ...or end date exists and is between last monday and next monday (extract also
        # events which end during the week/weeks)
        | (
            Event.end_date.is_not(null())
            & (Event.end_date >= last_monday)
            & (Event.end_date < next_monday)
        )
    ])

    statement = select(Event).filter(*filters).order_by(
        Event.start_year,
        Event.start_month,
        Event.start_day,
        Event.message_id
    )

    return session.scalars(statement), last_monday, next_monday


def get_all_events(session: Session):
    statement = select(Event).where().order_by(
        Event.start_year,
        Event.start_month,
        Event.start_day,
        Event.message_id
    )

    return session.scalars(statement)
