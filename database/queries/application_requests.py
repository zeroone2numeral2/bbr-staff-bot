from typing import Optional

from sqlalchemy import null, false
from sqlalchemy.orm import Session

from database.models import ApplicationRequest


def get_open(session: Session, user_id: int) -> Optional[ApplicationRequest]:
    request: ApplicationRequest = (
        session.query(ApplicationRequest)
        .filter(
            ApplicationRequest.user_id == user_id,
            ApplicationRequest.status == null()  # only pending requests
        )
        .oder_by(ApplicationRequest.id.desc())
        .one_or_none()
    )

    return request


def get_by_id(session: Session, application_request_id: int) -> Optional[ApplicationRequest]:
    request: ApplicationRequest = session.query(ApplicationRequest).filter(ApplicationRequest.id == application_request_id).one_or_none()

    return request


def get_user_requests(session: Session, user_id: int):
    return session.query(ApplicationRequest).filter(
        ApplicationRequest.user_id == user_id,
        ((ApplicationRequest.reset == false()) | (ApplicationRequest.reset == null()))
    ).all()
