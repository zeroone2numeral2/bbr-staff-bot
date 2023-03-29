from typing import Optional, List, Tuple, Union

from sqlalchemy import true, false
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from telegram import ChatMemberAdministrator, ChatMemberOwner, ChatMember

from database.models import Setting, Chat, ChatAdministrator, chat_members_to_dict
from constants import Language


def get_staff_chat(session: Session) -> Optional[Chat]:
    chat: Chat = session.query(Chat).filter(Chat.default == true()).one_or_none()
    return chat


def update_administrators(session: Session, chat: Chat, administrators: Tuple[ChatMember]):
    current_chat_administrators_dict = chat_members_to_dict(chat.chat_id, administrators)

    chat_administrators = []
    for _, chat_member_dict in current_chat_administrators_dict.items():
        chat_administrator = ChatAdministrator(**chat_member_dict)
        chat_administrators.append(chat_administrator)

    # this also deletes the instances of ChatAdministrator currently not in 'current_chat_administrators_dict'
    chat.chat_administrators = chat_administrators
    chat.last_administrators_fetch = func.now()

    session.add(chat)  # https://docs.sqlalchemy.org/en/13/orm/cascades.html#save-update

