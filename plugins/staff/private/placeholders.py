import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, filters, PrefixHandler

import decorators
import utilities
from constants import COMMAND_PREFIXES, Group
from replacements import PLACEHOLDER_REPLACEMENTS_TELEGRAM_USER, PLACEHOLDER_REPLACEMENTS_DATABASE

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_placeholders_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/placeholders {utilities.log(update)}")

    text = ""
    for placeholder, _ in {**PLACEHOLDER_REPLACEMENTS_TELEGRAM_USER, **PLACEHOLDER_REPLACEMENTS_DATABASE}.items():
        text += "• <code>{" + placeholder + "}</code>\n"

    text += "\nHold on a placeholder to quickly copy it"

    await update.message.reply_text(text)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ['placeholders', 'ph'], on_placeholders_command, filters.ChatType.PRIVATE), Group.NORMAL),
)
