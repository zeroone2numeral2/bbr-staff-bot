import logging
import re
from typing import Optional, List, Iterable

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from database.models import User, Chat
from database.queries import users, chats
import decorators
import utilities
from constants import Group
from emojis import Emoji
from ext.filters import Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/chats {utilities.log(update)}")

    chats_list: Iterable[Chat] = chats.get_core_chats(session)
    lines = []
    for chat in chats_list:
        chat_text = f"• <b>{chat.type_pretty()}</b>: {utilities.escape_html(chat.title)} [<code>{chat.chat_id}</code>]"
        lines.append(chat_text)

    await update.message.reply_text("\n".join(lines))


HANDLERS = (
    (CommandHandler(["chats"], on_chats_command, filters=Filter.SUPERADMIN), Group.NORMAL),
)
