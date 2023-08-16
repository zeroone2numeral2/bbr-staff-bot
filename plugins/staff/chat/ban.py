import logging
import re

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import filters, PrefixHandler, ContextTypes

from ext.filters import ChatFilter
from database.models import Chat, UserMessage
from database.queries import user_messages
import decorators
import utilities
from constants import COMMAND_PREFIXES, Group

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/ban or /shadowban {utilities.log(update)}")

    if not update.message.reply_to_message.from_user or update.message.reply_to_message.from_user.id == context.bot.id:
        await update.effective_message.reply_text("Reply to an user's message")
        return

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    logger.info("banning user...")
    reason = utilities.get_argument(["ban", "shadowban"], update.message.text) or None
    shadowban = bool(re.search(rf"[{COMMAND_PREFIXES}]shadowban", update.message.text, re.I))

    user_message.user.ban(reason=reason, shadowban=shadowban)

    text = f"User {utilities.escape_html(user_message.user.name)} {'shadow' if shadowban else ''}banned, reason: {reason or '-'}\n" \
           f"#id{user_message.user.user_id}"

    await update.effective_message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"/unban {utilities.log(update)}")

    if not update.message.reply_to_message.from_user or update.message.reply_to_message.from_user.id == context.bot.id:
        await update.effective_message.reply_text("Reply to an user's message")
        return

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    user_message.user.unban()
    await update.effective_message.reply_text(f"User unbanned")


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ['ban', 'shadowban'], on_ban_command, ChatFilter.STAFF & filters.REPLY), Group.NORMAL),
    (PrefixHandler(COMMAND_PREFIXES, 'unban', on_unban_command, ChatFilter.STAFF & filters.REPLY), Group.NORMAL),
)
