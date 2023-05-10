import logging
import re
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, filters

from database.models import User
from database.queries import users
import decorators
import utilities
from constants import Group
from emojis import Emoji
from config import config
from ext.filters import Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_app_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/app {utilities.log(update)}")

    if not update.message.reply_to_message.from_user or update.message.reply_to_message.from_user.is_bot:
        await update.message.reply_text("rispondi ad un utente non bot e non anonimo")
        return

    target_user = update.message.reply_to_message.from_user
    user: User = users.get_safe(session, target_user, commit=True)
    if user.can_evaluate_applications:
        user.can_evaluate_applications = False
        await update.message.reply_html(f"l'utente non potrà più approvare le richieste")
    else:
        user.can_evaluate_applications = True
        await update.message.reply_html(f"utente abilitato all'approvazione delle richieste")


HANDLERS = (
    (CommandHandler(["app"], on_app_command, filters=Filter.SUPERADMIN_AND_GROUP & filters.REPLY), Group.NORMAL),
)
