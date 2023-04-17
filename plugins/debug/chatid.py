import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, filters, CallbackQueryHandler

from constants import Group

logger = logging.getLogger(__name__)


async def on_chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{update.effective_chat.id}")


HANDLERS = (
    (CommandHandler('chatid', on_chatid_command), Group.DEBUG),
)
