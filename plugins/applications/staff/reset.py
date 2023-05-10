import logging
import re
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from database.models import User
from database.queries import users
import decorators
import utilities
from constants import Group
from emojis import Emoji

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/reset {utilities.log(update)}")

    user_id_match = re.search(r"(?:#user)?(?P<user_id>\d+)", update.message.text, re.I)
    if not user_id_match:
        await update.message.reply_text("impossibile rilevare l'id dell'utente")
        return

    user_id = int(user_id_match.group("user_id"))
    user: User = users.get_or_create(session, user_id, create_if_missing=False)
    if not user:
        await update.message.reply_text(f"impossibile trovare l'utente <code>{user_id}</code> nel database")
        return

    user.reset_evaluation()
    await update.message.reply_text(f"L'utente ora potrà richiedere nuovamente di essere ammesso al gruppo")


HANDLERS = (
    (CommandHandler(["reset"], on_reset_command), Group.NORMAL),
)
