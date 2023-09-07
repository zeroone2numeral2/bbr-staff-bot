import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram import ChatMember, ChatMemberMember, ChatMemberRestricted, ChatMemberLeft, ChatMemberBanned, ChatMemberAdministrator
from telegram.ext import ChatMemberHandler

from constants import Group
from database.models import Chat
from plugins.chat_members.common import (
    save_or_update_users_from_chat_member_update,
    save_chat_member
)
import decorators
import utilities

logger = logging.getLogger(__name__)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_my_chat_member_update(update: Update, _, session: Session, chat: Optional[Chat] = None):
    logger.info(f"my chat member update {utilities.log(update)}")

    logger.info("saving or updating User objects...")
    user_records = save_or_update_users_from_chat_member_update(session, update, commit=True)

    if update.effective_chat.id > 0:
        user = user_records[0]  # only one will be returned
        new_status = update.my_chat_member.new_chat_member.status
        logger.info(f"MyChatMember update from private chat, new status: {new_status}")
        if new_status == ChatMember.BANNED:
            user.set_stopped()
        elif new_status == ChatMember.MEMBER:
            user.set_restarted()
        else:
            logger.warning(f"unhandled new status from MyChatMember update: {new_status}")
    else:
        logger.info(f"MyChatMember update in a group chat, new status: {update.my_chat_member.new_chat_member.status}")
        if isinstance(update.my_chat_member.new_chat_member, ChatMemberAdministrator):
            chat.set_as_administrator(
                can_delete_messages=update.my_chat_member.new_chat_member.can_delete_messages,
                can_invite_users=update.my_chat_member.new_chat_member.can_invite_users
            )
        elif isinstance(update.my_chat_member.new_chat_member, (ChatMemberMember, ChatMemberRestricted)):
            chat.unset_as_administrator()
        elif isinstance(update.my_chat_member.new_chat_member, (ChatMemberLeft, ChatMemberBanned)):
            chat.set_left()

        logger.info("saving new chat_member object...")
        save_chat_member(session, update)


HANDLERS = (
    (ChatMemberHandler(on_my_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER), Group.NORMAL),
)
