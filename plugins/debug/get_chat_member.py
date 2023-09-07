import json
import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import decorators
import utilities
from constants import Group
from database.models import Chat
from database.queries import chats

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_getcm_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    users_chat = chats.get_chat(session, Chat.is_users_chat)
    user_id = int(context.args[0])
    logger.info(f"user id: {user_id}")

    chat_member = await context.bot.get_chat_member(users_chat.chat_id, user_id)
    await update.message.reply_text(f"<code>{utilities.escape(json.dumps(chat_member.to_dict(), indent=2))}</code>")


HANDLERS = (
    (CommandHandler('getcm', on_getcm_command), Group.DEBUG),
)
