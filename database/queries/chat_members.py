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


def get_chat_administrators(session: Session, chat_id: int):
    # noinspection PyUnresolvedReferences

    statement = session.query(DbChatMember).where(
        DbChatMember.chat_id == chat_id,
        Chat.status in (TgChatMember.ADMINISTRATOR, TgChatMember.OWNER)
    )

    return session.scalars(statement)
