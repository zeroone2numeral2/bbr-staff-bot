from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, filters


async def on_chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{update.effective_chat.id}")


HANDLERS = (
    (CommandHandler('chatid', on_chatid_command, filters.ChatType.PRIVATE), Group.DEBUG),
)
