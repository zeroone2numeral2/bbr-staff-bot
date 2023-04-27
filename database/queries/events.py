from typing import Optional

from sqlalchemy.orm import Session

from database.models import Event


def get_or_create(session: Session, chat_id: int, message_id: int, create_if_missing=True, commit=False) -> Optional[Event]:
    event: Event = session.query(Event).filter(Event.chat_id == chat_id, Event.message_id == message_id).one_or_none()

    if not event and create_if_missing:
        event = Event(chat_id, message_id)
        session.add(event)
        if commit:
            session.commit()

    return event
