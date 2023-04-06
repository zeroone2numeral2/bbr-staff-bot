from typing import Optional, List, Tuple, Union

from sqlalchemy import true, false, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from telegram import ChatMemberAdministrator, ChatMemberOwner, ChatMember

from database.models import Chat, ChatMember as DbChatMember, chat_members_to_dict
from constants import Language


def get_staff_chat(session: Session) -> Optional[Chat]:
    chat: Chat = session.query(Chat).filter(Chat.default == true()).one_or_none()
    return chat


def get_all_chats(session: Session):
    statement = select(Chat).where()
    return session.scalars(statement)


def get_staff_chat_administrators(session: Session):
    statement = session.query(DbChatMember).join(Chat).where(
        DbChatMember.status.in_([ChatMember.ADMINISTRATOR, ChatMember.OWNER]),
        Chat.is_staff_chat == true()
    )
    return session.scalars(statement)


"""
def update_administrators_old(session: Session, chat: Chat, administrators: Tuple[ChatMember]):
    current_chat_administrators_dict = chat_members_to_dict(chat.chat_id, administrators)

    chat_administrators = []
    for _, chat_member_dict in current_chat_administrators_dict.items():
        chat_administrator = ChatAdministrator(**chat_member_dict)
        chat_administrators.append(chat_administrator)

    # this also deletes the instances of ChatAdministrator currently not in 'current_chat_administrators_dict'
    chat.chat_administrators = chat_administrators
    chat.last_administrators_fetch = func.now()

    session.add(chat)  # https://docs.sqlalchemy.org/en/13/orm/cascades.html#save-update
"""


def update_administrators(session: Session, chat: Chat, administrators: Tuple[ChatMember]):
    current_chat_administrators_dict = chat_members_to_dict(chat.chat_id, administrators)

    for _, chat_member_dict in current_chat_administrators_dict.items():
        chat_administrator = DbChatMember(**chat_member_dict)
        session.merge(chat_administrator)

