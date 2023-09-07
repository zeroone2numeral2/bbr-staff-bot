import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from constants import Group

logger = logging.getLogger(__name__)


async def on_chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(f"<code>{update.effective_chat.id}</code>")


async def on_fileid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = update.message.reply_to_message.effective_attachment[-1].file_id if update.message.reply_to_message.photo else update.message.reply_to_message.effective_attachment.file_id
    await update.message.reply_html(f"<code>{file_id}</code>")


HANDLERS = (
    (CommandHandler('chatid', on_chatid_command), Group.DEBUG),
    (CommandHandler('fileid', on_fileid_command), Group.DEBUG),
)
