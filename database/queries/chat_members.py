from typing import Optional, List, Tuple, Union, Iterable

from sqlalchemy import true, false, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from telegram import ChatMemberAdministrator, ChatMemberOwner, ChatMember

from database.models import Chat, ChatMember as DbChatMember, chat_members_to_dict
from constants import Language


CHAT_MEMBER_STATUS_ADMIN = [ChatMember.ADMINISTRATOR, ChatMember.OWNER]

CHAT_MEMBER_STATUS_MEMBER = [ChatMember.ADMINISTRATOR, ChatMember.OWNER, ChatMember.MEMBER, ChatMember.RESTRICTED]


def save_administrators(session: Session, chat_id: int, administrators: Iterable[Union[ChatMemberAdministrator, ChatMemberOwner]]):
    chat_administrators_dict = chat_members_to_dict(chat_id, administrators)

    for _, chat_member_dict in chat_administrators_dict.items():
        chat_administrator = DbChatMember(**chat_member_dict)
        session.merge(chat_administrator)


def is_staff_chat_admin(session: Session, user_id: int) -> Optional[DbChatMember]:
    chat_member = session.query(DbChatMember).join(Chat).where(
        DbChatMember.user_id == user_id,
        DbChatMember.status.in_(CHAT_MEMBER_STATUS_ADMIN),
        Chat.is_staff_chat == true()
    ).one_or_none()

    return chat_member


def is_users_chat_member(session: Session, user_id: int) -> Optional[DbChatMember]:
    chat_member = session.query(DbChatMember).join(Chat).where(
        DbChatMember.user_id == user_id,
        DbChatMember.status.in_(CHAT_MEMBER_STATUS_MEMBER),
        Chat.is_users_chat == true()
    ).one_or_none()

    return chat_member
