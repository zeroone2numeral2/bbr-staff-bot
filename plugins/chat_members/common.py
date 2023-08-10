import logging
from typing import List

from sqlalchemy.orm import Session
from telegram import Update

from database.models import User, ChatMember as DbChatMember
from database.queries import users

logger = logging.getLogger(__name__)


def save_or_update_users_from_chat_member_update(session: Session, update: Update, commit=False) -> List[User]:
    users_to_save = []
    if update.chat_member:
        users_to_save = [update.chat_member.from_user, update.chat_member.new_chat_member.user]
    elif update.my_chat_member:
        users_to_save = [update.my_chat_member.from_user]

    user_records = []
    for telegram_user in users_to_save:
        user = users.get_or_create(session, telegram_user.id, create_if_missing=False)
        if not user:
            user = User(telegram_user)
            session.add(user)
        else:
            user.update_metadata(telegram_user)
        user_records.append(user)

    if commit:
        session.commit()

    return user_records


def save_chat_member(session: Session, update: Update, commit=False) -> DbChatMember:
    if update.chat_member:
        logger.debug(f"saving ChatMember, new user status: <{update.chat_member.new_chat_member.status}>")
        # from pprint import pprint
        # pprint(update.chat_member.to_dict())
        chat_member_to_save = update.chat_member.new_chat_member
    elif update.my_chat_member:
        logger.debug(f"saving MyChatMember, new bot status: <{update.my_chat_member.new_chat_member.status}>")
        # from pprint import pprint
        # pprint(update.my_chat_member.to_dict())
        chat_member_to_save = update.my_chat_member.new_chat_member
    else:
        raise ValueError("couldn't find ChatMember to save")

    chat_member_record = DbChatMember.from_chat_member(update.effective_chat.id, chat_member_to_save)
    session.merge(chat_member_record)

    if commit:
        session.commit()

    return chat_member_record
