import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes
from telegram.ext import PrefixHandler
from telegram.ext import filters

import decorators
import utilities
from constants import ADMIN_HELP, COMMAND_PREFIXES, Group
from database.models import User, Chat
from database.queries import chat_members
from plugins.users.start import on_start_command

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/help {utilities.log(update)}")

    if not chat_members.is_member(session, update.effective_user.id, Chat.is_staff_chat, is_admin=True):
        logger.debug("user is not admin")
        return await on_start_command(update, context)

    await update.message.reply_text(ADMIN_HELP)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, 'help', on_help_command, filters.ChatType.PRIVATE), Group.NORMAL),
)
