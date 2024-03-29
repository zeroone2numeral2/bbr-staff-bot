from typing import Optional

from sqlalchemy import false
from sqlalchemy.orm import Session

from database.models import PartiesMessage


def get_last_parties_message(session: Session, chat_id: int, events_type: str):
    parties_message: Optional[PartiesMessage] = (session.query(PartiesMessage).filter(
        PartiesMessage.chat_id == chat_id,
        PartiesMessage.events_type == events_type,
        PartiesMessage.deleted == false(),
        PartiesMessage.ignore == false()
    ).order_by(PartiesMessage.message_date.desc()).first())

    return parties_message


def get_parties_message(session: Session, chat_id: int, message_id: int):
    parties_message: Optional[PartiesMessage] = session.query(PartiesMessage).filter(
        PartiesMessage.chat_id == chat_id,
        PartiesMessage.message_id == message_id,
        PartiesMessage.deleted == false(),
        PartiesMessage.ignore == false()
    ).one_or_none()

    return parties_message
