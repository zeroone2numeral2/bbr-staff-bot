from typing import Optional, Union, Iterable

from sqlalchemy import true
from sqlalchemy.orm import Session
from telegram import ChatMemberAdministrator, ChatMemberOwner, ChatMember

from database.models import Chat, ChatMember as DbChatMember, chat_members_to_dict
from database.queries import users

CHAT_MEMBER_STATUS_ADMIN = [ChatMember.ADMINISTRATOR, ChatMember.OWNER]

CHAT_MEMBER_STATUS_MEMBER = [ChatMember.ADMINISTRATOR, ChatMember.OWNER, ChatMember.MEMBER, ChatMember.RESTRICTED]


def save_administrators(session: Session, chat_id: int, administrators: Iterable[Union[ChatMemberAdministrator, ChatMemberOwner]], save_users=True):
    if save_users:
        for administrator in administrators:
            # mae sure we have the User model for that user
            users.get_safe(session, administrator.user)

    chat_administrators_dict = chat_members_to_dict(chat_id, administrators)

    for _, chat_member_dict in chat_administrators_dict.items():
        chat_administrator = DbChatMember(**chat_member_dict)
        session.merge(chat_administrator)


def is_member(session: Session, user_id: int, chat_filter, is_admin=False) -> Optional[DbChatMember]:
    filters = [DbChatMember.user_id == user_id, chat_filter == true()]
    if is_admin:
        # noinspection PyUnresolvedReferences
        filters.append(DbChatMember.status.in_(CHAT_MEMBER_STATUS_ADMIN))
    else:
        # noinspection PyUnresolvedReferences
        filters.append(DbChatMember.status.in_(CHAT_MEMBER_STATUS_MEMBER))

    chat_member = session.query(DbChatMember).join(Chat).filter(*filters).one_or_none()

    return chat_member


def get_chat_member(session: Session, user_id: int, chat_filter) -> Optional[DbChatMember]:
    chat_member = session.query(DbChatMember).join(Chat).filter(
        DbChatMember.user_id == user_id,
        chat_filter == true()
    ).one_or_none()

    return chat_member


def get_chat_member_by_id(session: Session, user_id: int, chat_id: int) -> Optional[DbChatMember]:
    chat_member = session.query(DbChatMember).filter(
        DbChatMember.user_id == user_id,
        DbChatMember.chat_id == chat_id
    ).one_or_none()

    return chat_member


def get_user_chat_members(session: Session, user_id: int):
    query = session.query(DbChatMember).join(Chat).filter(
        DbChatMember.user_id == user_id
    )

    return session.scalars(query)


def get_chat_chat_members(session: Session, chat_filter, admins_only: bool = False):
    filters = [chat_filter == true()]
    if admins_only:
        filters.append(DbChatMember.status.in_(CHAT_MEMBER_STATUS_ADMIN))

    query = session.query(DbChatMember).join(Chat).filter(*filters)

    return session.scalars(query)
