import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes
from telegram.ext import filters
from telegram.ext import PrefixHandler

from database.models import User
from database.queries import chat_members
import decorators
import utilities
from plugins.users.start import on_start_command
from constants import ADMIN_HELP, COMMAND_PREFIXES, Group

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/help {utilities.log(update)}")

    if not chat_members.is_staff_chat_admin(session, update.effective_user.id):
        logger.debug("user is not admin")
        return await on_start_command(update, context)

    await update.message.reply_text(ADMIN_HELP)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, 'help', on_help_command, filters.ChatType.PRIVATE), Group.NORMAL),
)
