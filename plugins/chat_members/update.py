import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update
from telegram import ChatMember, ChatMemberMember, ChatMemberRestricted, ChatMemberLeft, ChatMemberBanned, ChatMemberAdministrator
from telegram.ext import ChatMemberHandler

from constants import Group
from database.models import User, Chat, ChatMember as DbChatMember
from database.queries import users
import decorators
import utilities

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


def save_chat_member(session: Session, update: Update, commit=False):
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


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_chat_member_update(update: Update, _, session: Session, chat: Optional[Chat] = None):
    logger.info(f"chat member update {utilities.log(update)}")

    logger.info("saving or updating User objects...")
    user_records = save_or_update_users_from_chat_member_update(session, update, commit=True)

    if update.effective_chat.id > 0 and update.my_chat_member:
        user = user_records[0]  # only one will be returned
        new_status = update.my_chat_member.new_chat_member.status
        logger.info(f"ChatMember update from private chat, new status: {new_status}")
        if new_status == ChatMember.BANNED:
            user.set_stopped()
        elif new_status == ChatMember.MEMBER:
            user.set_restarted()
        else:
            logger.warning(f"unhandled new status from MyChatMember update: {new_status}")
        return

    logger.info("saving new chat_member object...")
    save_chat_member(session, update)

    if update.my_chat_member:
        logger.info(f"MyChatMember update, new status: {update.my_chat_member.new_chat_member.status}")
        if isinstance(update.my_chat_member.new_chat_member, ChatMemberAdministrator):
            chat.set_as_administrator(update.my_chat_member.new_chat_member.can_delete_messages)
        elif isinstance(update.my_chat_member.new_chat_member, (ChatMemberMember, ChatMemberRestricted)):
            chat.unset_as_administrator()
        elif isinstance(update.my_chat_member.new_chat_member, (ChatMemberLeft, ChatMemberBanned)):
            chat.set_left()


HANDLERS = (
    (ChatMemberHandler(on_chat_member_update, ChatMemberHandler.ANY_CHAT_MEMBER), Group.NORMAL),
)
