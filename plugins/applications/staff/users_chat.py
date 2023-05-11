import logging
from typing import Tuple

from sqlalchemy.orm import Session
from telegram import Update, ChatMember
from telegram.ext import filters, PrefixHandler

from database.models import Chat
from database.queries import chats, users
import decorators
import utilities
from constants import COMMAND_PREFIXES, Group
from ext.filters import ChatFilter, Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_setuserschat_command(update: Update, _, session: Session, chat: Chat):
    logger.info(f"/setuserschat {utilities.log(update)}")

    if not utilities.is_superadmin(update.effective_user):
        logger.warning(f"user {utilities.log_string_user(update.effective_user)}) tried to use /setuserschat")
        return

    chats.reset_users_chat(session)
    session.commit()

    chat.set_as_users_chat()
    session.commit()  # make sure to commit now, just in case something unexpected happens while saving admins

    ChatFilter.USERS.chat_ids = {chat.chat_id}

    await update.message.reply_text("This group has been set as the users chat")

    logger.info("saving administrators...")
    administrators: Tuple[ChatMember] = await update.effective_chat.get_administrators()
    chats.update_administrators(session, chat, administrators)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ["setuserschat", "suc"], on_setuserschat_command, Filter.SUPERADMIN_AND_GROUP), Group.NORMAL),
)
