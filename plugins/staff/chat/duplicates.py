import logging
from typing import List

from sqlalchemy.orm import Session
from telegram import Update, Chat
from telegram.error import BadRequest
from telegram.ext import ContextTypes, MessageHandler, CommandHandler
from telegram.ext import filters

from database.models import User, PrivateChatMessage, StaffChatMessage
import decorators
import utilities
from constants import Group
from database.queries import private_chat_messages, staff_chat_messages
from ext.filters import ChatFilter, Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True, pass_down_db_instances=True)
async def on_staff_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"saving/updating staff chat message {utilities.log(update)}")
    message = update.effective_message

    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        logger.debug("ignoring reply to bot's message")
        return

    staff_chat_message = staff_chat_messages.get_or_create(session, message, commit=True)
    if message.edit_date:
        logger.debug("edited message: updating message metadata")
        staff_chat_message.update_message_metadata(message)

    duplicates = staff_chat_messages.find_duplicates(session, message)

    if not duplicates:
        return

    logger.info(f"found {len(duplicates)} duplicates")
    duplicates_links = [d.message_link_html(f"{utilities.format_datetime(d.message_date, format_str='%d/%m')}") for d in duplicates]
    text = f"Sembra che questo messaggio sia già stato inviato in passato: {', '.join(duplicates_links)}"
    await update.message.reply_text(text, quote=True)


HANDLERS = (
    (MessageHandler(ChatFilter.STAFF & Filter.MESSAGE_OR_EDIT, on_staff_chat_message), Group.PREPROCESS),
)
