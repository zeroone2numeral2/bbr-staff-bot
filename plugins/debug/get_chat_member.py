import json
import logging

from sqlalchemy.orm import Session
from telegram import Update, ChatMemberMember, ChatMemberLeft, ChatMemberBanned
from telegram.ext import ContextTypes, CommandHandler

import decorators
import utilities
from constants import Group
from database.models import Chat, User, ChatMember as DbChatMember
from database.queries import chats, users, chat_members

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_getcm_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    users_chat = chats.get_chat(session, Chat.is_users_chat)
    user_id = utilities.get_user_id_from_text(update.message.text)
    logger.info(f"user id: {user_id}")

    chat_member = await context.bot.get_chat_member(users_chat.chat_id, user_id)
    await update.message.reply_text(f"<code>{utilities.escape(json.dumps(chat_member.to_dict(), indent=2))}</code>")

    logger.info(f"creating/updating User instance...")
    users.get_safe(session, chat_member.user, update_metadata_if_existing=True, commit=True)

    if isinstance(chat_member, (ChatMemberMember, ChatMemberLeft, ChatMemberBanned)):
        # if it's an instance of these types, telegram doesn't return the user's permissions, because they
        # are the default group's permissions (member) or they do not apply (left/banned)
        logger.info("chat_member is an instance of ChatMemberMember/ChatMemberLeft/ChatMemberBanned")

    logger.info("saving chat_member object...")
    chat_member_record = DbChatMember.from_chat_member(users_chat.chat_id, chat_member)
    session.merge(chat_member_record)
    session.commit()

    await update.message.reply_text(f"ChatMember created/updated")


HANDLERS = (
    (CommandHandler('getcm', on_getcm_command), Group.DEBUG),
)
