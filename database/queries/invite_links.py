from typing import Optional

from sqlalchemy import false
from sqlalchemy.orm import Session

from database.models import InviteLink, Destination


def get_invite_link(session: Session, invite_link: str):
    invite_link_record: Optional[InviteLink] = session.query(InviteLink).filter(
        InviteLink.invite_link == invite_link
    ).one_or_none()

    return invite_link_record


def get_last_unused_invite_link(session: Session, chat_id: int, user_id: int, destination: str):
    invite_link: Optional[InviteLink] = (session.query(InviteLink).filter(
        InviteLink.sent_to_user_user_id == user_id,
        InviteLink.chat_id == chat_id,
        InviteLink.destination == destination,
        InviteLink.is_revoked == false(),
        InviteLink.sent_to_user_link_removed == false()
    ).order_by(InviteLink.link_id.desc()).first())

    return invite_link


def get_most_recent_invite_link(session: Session, chat_id: int, user_id: int, destination: str):
    invite_link_record: Optional[InviteLink] = session.query(InviteLink).filter(
        InviteLink.sent_to_user_user_id == user_id,
        InviteLink.chat_id == chat_id,
        InviteLink.destination == destination,
    ).order_by(InviteLink.created_on.desc()).first()

    return invite_link_record

