from typing import Optional, Tuple

from sqlalchemy import true, select, update, or_
from sqlalchemy.orm import Session
from telegram import Chat as TelegramChat
from telegram import ChatMember

from database.models import Chat, ChatMember as DbChatMember, chat_members_to_dict
from database.queries import users


def get_chat(session: Session, chat_filter) -> Optional[Chat]:
    chat: Optional[Chat] = session.query(Chat).filter(chat_filter == true()).one_or_none()
    return chat


def get_core_chats(session: Session):
    query = session.query(Chat).filter(or_(
        Chat.is_staff_chat == true(),
        Chat.is_evaluation_chat == true(),
        Chat.is_users_chat == true(),
        Chat.is_log_chat == true(),
        Chat.is_modlog_chat == true(),
        Chat.is_events_chat == true(),
        Chat.network_chat == true(),
    ))

    return session.scalars(query)


def reset_staff_chat(session: Session):
    session.execute(update(Chat).values(is_staff_chat=False))


def reset_users_chat(session: Session):
    session.execute(update(Chat).values(is_users_chat=False))


def reset_log_chat(session: Session):
    session.execute(update(Chat).values(is_log_chat=False))


def reset_modlog_chat(session: Session):
    session.execute(update(Chat).values(is_modlog_chat=False))


def reset_events_chat(session: Session):
    session.execute(update(Chat).values(is_events_chat=False))


def reset_evaluation_chat(session: Session):
    session.execute(update(Chat).values(is_evaluation_chat=False))


def get_all_chats(session: Session):
    statement = select(Chat).where()
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


def update_administrators(session: Session, chat: Chat, administrators: Tuple[ChatMember], save_users=True):
    if save_users:
        for administrator in administrators:
            # mae sure we have the User model for that user
            users.get_safe(session, administrator.user)

    chat_administrators_dict = chat_members_to_dict(chat.chat_id, administrators)

    for _, chat_member_dict in chat_administrators_dict.items():
        chat_administrator = DbChatMember(**chat_member_dict)
        session.merge(chat_administrator)

