import datetime
from typing import Optional, List, Any, Tuple

from sqlalchemy import select, false, null, true
from sqlalchemy.orm import Session
from telegram import Message

import utilities
from config import config
from database.models import Event, Chat


def get_or_create(session: Session, chat_id: int, message_id: int, create_if_missing=True, commit=False) -> Optional[Event]:
    event: Event = session.query(Event).filter(Event.chat_id == chat_id, Event.message_id == message_id).one_or_none()

    if not event and create_if_missing:
        event = Event(chat_id, message_id)
        session.add(event)
        if commit:
            session.commit()

    return event


def get_event_from_discussion_group_message(session: Session, message: Message) -> Optional[Event]:
    return session.query(Event).filter(
        Event.discussion_group_chat_id == message.chat.id,
        Event.discussion_group_message_id == message.message_thread_id
    ).one_or_none()


def get_event_from_discussion_group_message_id(session: Session, chat_id: int, message_id: int) -> Optional[Event]:
    return session.query(Event).filter(
        Event.discussion_group_chat_id == chat_id,
        Event.discussion_group_message_id == message_id
    ).one_or_none()


def get_events(
        session: Session,
        skip_canceled: bool = False,
        filters: Optional[List] = None,
        order_by: Optional[List] = None  # list of Event class property to use as order_by
):
    if not filters:
        filters = []

    if not config.settings.allow_events_from_any_chat:
        filters.append(Chat.is_events_chat == true())

    filters.append(Event.deleted == false())

    if skip_canceled:
        filters.append(Event.canceled == false())

    if not order_by:
        order_by = []

    query = select(Event).join(Chat).filter(*filters).order_by(*order_by)
    # print(query)

    return session.scalars(query)


def get_week_events(session: Session, now: datetime.datetime, filters: List, weeks: int = 1) -> Tuple[Any, datetime.datetime, datetime.datetime]:
    additional_days = 0 if weeks <= 1 else 7 * weeks

    last_monday = utilities.previous_weekday(today=now.date(), weekday=0)
    next_monday = utilities.next_weekday(today=now.date(), weekday=0, additional_days=additional_days)

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

    filters.append(Event.deleted == false())

    statement = select(Event).filter(*filters).order_by(
        Event.start_year,
        Event.start_month,
        Event.start_day,
        Event.event_title,
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
