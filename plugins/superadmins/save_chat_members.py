import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from database.models import Chat
import decorators
import utilities
from constants import Group
from ext.filters import Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_savechatmembers_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"/savechatmembers (private) {utilities.log(update)}")

    await utilities.delete_messages_safe(update.message)  # delete as soon as possible

    text = f"{utilities.escape_html(update.effective_chat.title)} -> "
    if chat.save_chat_members:
        text += "false"
        chat.save_chat_members = False
    else:
        text += "true"
        chat.save_chat_members = True

    await context.bot.send_message(update.effective_user.id, text)


HANDLERS = (
    (CommandHandler(["savechatmembers", "scm"], on_savechatmembers_command, filters=Filter.SUPERADMIN_AND_GROUP), Group.NORMAL),
)
