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

    if not utilities.is_reply_to_user(update.message):
        await update.message.reply_text("rispondi ad un utente non bot e non anonimo")
        return

    target_user = update.message.reply_to_message.from_user
    mention = utilities.mention_escaped(target_user)
    user: User = users.get_safe(session, target_user, commit=True)
    if user.can_evaluate_applications:
        user.can_evaluate_applications = False
        text = f"{mention} non potrà più approvare le richieste"

    else:
        user.can_evaluate_applications = True
        text = f"{mention} abilitato all'approvazione delle richieste"

    await update.message.reply_html(text, quote=True)


HANDLERS = (
    (CommandHandler(["app"], on_app_command, filters=Filter.SUPERADMIN_AND_GROUP & filters.REPLY), Group.NORMAL),
)
