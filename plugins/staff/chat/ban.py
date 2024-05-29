import logging
import re
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import filters, ContextTypes, CommandHandler

import decorators
import utilities
from constants import COMMAND_PREFIXES, Group
from database.models import Chat, User
from database.queries import common
from ext.filters import ChatFilter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/ban or /shadowban {utilities.log(update)}")

    user: Optional[User] = await common.get_user_instance_from_message(update, context, session)
    if not user:
        return

    logger.info(f"banning user {user.full_name()} ({user.user_id})...")
    reason = utilities.get_argument(
        update.message.text,
        commands=["ban", "shadowban"],
        bot_username=context.bot.username,
        remove_user_id_hashtag=True
    ) or None
    shadowban = bool(re.search(rf"[{COMMAND_PREFIXES}]shadowban", update.message.text, re.I))

    user.ban(reason=reason, shadowban=shadowban)

    text = f"User {utilities.escape_html(user.name)} {'shadow' if shadowban else ''}banned, reason: {reason or '-'}\n" \
           f"#id{user.user_id}"

    await update.effective_message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session()
async def on_unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/unban {utilities.log(update)}")

    user: Optional[User] = await common.get_user_instance_from_message(update, context, session)
    if not user:
        return

    user.unban()
    await update.effective_message.reply_text(f"User unbanned")


HANDLERS = (
    (CommandHandler(['ban', 'shadowban'], on_ban_command, (ChatFilter.STAFF | ChatFilter.EVALUATION) & filters.REPLY), Group.NORMAL),
    (CommandHandler('unban', on_unban_command, (ChatFilter.STAFF | ChatFilter.EVALUATION) & filters.REPLY), Group.NORMAL),
)
