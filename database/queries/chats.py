from typing import Optional, Tuple

from sqlalchemy import true, select, update
from sqlalchemy.orm import Session
from telegram import ChatMember
from telegram import Chat as TelegramChat

from database.models import Chat, ChatMember as DbChatMember, chat_members_to_dict, User


def get_staff_chat(session: Session) -> Optional[Chat]:
    chat: Chat = session.query(Chat).filter(Chat.is_staff_chat == true()).one_or_none()
    return chat


def reset_staff_chat(session: Session):
    session.execute(update(Chat).values(is_staff_chat=False))


def reset_users_chat(session: Session):
    session.execute(update(Chat).values(is_users_chat=False))


def get_users_chat(session: Session) -> Optional[Chat]:
    chat: Chat = session.query(Chat).filter(Chat.is_users_chat == true()).one_or_none()
    return chat


def get_all_chats(session: Session):
    statement = select(Chat).where()
    return session.scalars(statement)


def get_staff_chat_administrators(session: Session):
    # noinspection PyUnresolvedReferences
    statement = session.query(DbChatMember).join(Chat).join(User).where(
        DbChatMember.status.in_([ChatMember.ADMINISTRATOR, ChatMember.OWNER]),
        Chat.is_staff_chat == true()
    )
    return session.scalars(statement)


def get_or_create(session: Session, chat_id: int, create_if_missing=True, telegram_chat: Optional[TelegramChat] = None):
    chat: Chat = session.query(Chat).filter(Chat.chat_id == chat_id).one_or_none()

    if not chat and create_if_missing:
        chat = Chat(telegram_chat)
        session.add(chat)

    return chat


def get_safe(session: Session, telegram_chat: TelegramChat, create_if_missing=True, update_metadata_if_existing=True, commit=False):
    chat: Chat = session.query(Chat).filter(Chat.chat_id == telegram_chat.id).one_or_none()

    if not chat and create_if_missing:
        chat = Chat(telegram_chat)
        session.add(chat)
    elif chat and update_metadata_if_existing:
        chat.update_metadata(telegram_chat)

    if commit:
        session.commit()

    return chat


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

