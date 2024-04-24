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


def get_from_log_channel_message(session: Session, log_message_chat_id: int, log_message_message_id: int) -> Optional[ApplicationRequest]:
    request: Optional[ApplicationRequest] = session.query(ApplicationRequest).filter(
        ApplicationRequest.log_message_chat_id == log_message_chat_id,
        ApplicationRequest.log_message_message_id == log_message_message_id
    ).one_or_none()

    return request


def get_from_evaluation_buttons_log_channel_message(session: Session, chat_id: int, message_id: int) -> Optional[ApplicationRequest]:
    request: Optional[ApplicationRequest] = session.query(ApplicationRequest).filter(
        ApplicationRequest.evaluation_buttons_message_chat_id == chat_id,
        ApplicationRequest.evaluation_buttons_message_message_id == message_id
    ).one_or_none()

    return request


def get_user_requests(session: Session, user_id: int):
    return session.query(ApplicationRequest).filter(
        ApplicationRequest.user_id == user_id,
        ((ApplicationRequest.reset == false()) | (ApplicationRequest.reset == null()))
    ).all()
