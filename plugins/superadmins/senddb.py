import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import decorators
import utilities
from constants import Group
from ext.filters import Filter

logger = logging.getLogger(__name__)

DB_FILE_PATH = r"bot.db"


@decorators.catch_exception()
async def on_senddb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/senddb {utilities.log(update)}")

    await update.message.reply_html(f"sending <code>{DB_FILE_PATH}</code>...")

    with open(DB_FILE_PATH, "rb") as fh:
        await update.message.reply_document(fh.read())


HANDLERS = (
    (CommandHandler(["senddb", "db"], on_senddb_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
