from typing import Optional

from sqlalchemy import false
from sqlalchemy.orm import Session

from database.models import InviteLink


def get_invite_link(session: Session, invite_link: str):
    invite_link_record: Optional[InviteLink] = session.query(InviteLink).filter(
        InviteLink.invite_link == invite_link
    ).one_or_none()

    return invite_link_record
