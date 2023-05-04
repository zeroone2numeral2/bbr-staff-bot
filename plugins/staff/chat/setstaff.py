import logging
from typing import Tuple

from sqlalchemy.orm import Session
from sqlalchemy import update as sqlalchemy_update
from telegram import Update, ChatMember
from telegram.ext import filters, PrefixHandler

from database.models import Chat
from database.queries import chats, users
import decorators
import utilities
from constants import COMMAND_PREFIXES, Group

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_setstaff_command(update: Update, _, session: Session, chat: Chat):
    logger.info(f"/setstaff {utilities.log(update)}")

    if not utilities.is_admin(update.effective_user):
        logger.warning(f"user {utilities.log_string_user(update.effective_user)}) tried to use /setstaff")
        return

    if "ssilent" in update.message.text.lower():
        # noinspection PyBroadException
        try:
            await update.message.delete()
        except:
            pass

    chats.reset_staff_chat(session)
    session.commit()

    chat.set_as_staff_chat()
    if "ssilent" not in update.message.text.lower():
        await update.message.reply_text("This group has been set as staff chat")

    session.commit()  # make sure to commit now, just in case something unexpected happens while saving admins

    logger.info("saving administrators...")
    administrators: Tuple[ChatMember] = await update.effective_chat.get_administrators()
    chats.update_administrators(session, chat, administrators)
    session.commit()
    for administrator in administrators:
        users.get_safe(session, administrator.user)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ['setstaff', 'ssilent'], on_setstaff_command, filters.ChatType.GROUPS), Group.NORMAL),
)
