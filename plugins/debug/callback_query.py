import logging

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from constants import Group

logger = logging.getLogger(__name__)


async def on_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.debug(f"{update.callback_query.data}")


HANDLERS = (
    (CallbackQueryHandler(on_callback_query, r".*"), Group.DEBUG),
)
