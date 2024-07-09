import logging

from telegram import Update, ReplyKeyboardMarkup, KeyboardButtonRequestChat, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kwargs = {"caption": ""}
    await context.bot.send_photo(
        chat_id=update.message.chat.id,
        photo=update.message.photo[-1].file_id,
        **kwargs
    )


async def on_chat_shared_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"{update.message.chat_shared}", reply_markup=ReplyKeyboardRemove())


def main() -> None:
    application = Application.builder().token(config.telegram.token).build()

    application.add_handler(MessageHandler(filters.PHOTO, on_photo))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
