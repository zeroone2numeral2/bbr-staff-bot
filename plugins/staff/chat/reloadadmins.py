import logging
from typing import Tuple

from sqlalchemy.orm import Session
from telegram import Update, ChatMember
from telegram.ext import CommandHandler

import decorators
import utilities
from constants import Group
from database.models import Chat
from database.queries import chats
from ext.filters import ChatFilter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_reloadadmins_command(update: Update, _, session: Session, chat: Chat):
    logger.info(f"/reloadadmins {utilities.log(update)}")

    logger.info("saving administrators...")
    administrators: Tuple[ChatMember] = await update.effective_chat.get_administrators()
    chats.update_administrators(session, chat, administrators)

    admins_names = [cm.user.first_name for cm in administrators]
    await update.effective_message.reply_text(f"Saved {len(administrators)} administrators ({', '.join(admins_names)})")


HANDLERS = (
    (CommandHandler('reloadadmins', on_reloadadmins_command, ChatFilter.STAFF | ChatFilter.USERS | ChatFilter.EVALUATION), Group.NORMAL),
)
