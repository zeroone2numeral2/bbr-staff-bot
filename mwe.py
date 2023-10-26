import logging

from telegram import Update, ReplyKeyboardMarkup, KeyboardButtonRequestChat, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    request_chat_button = KeyboardButtonRequestChat(
        request_id=1,
        chat_is_channel=False,
        bot_is_member=True  # clients should only show chats where the bot is member, right?
    )

    await update.effective_message.reply_text(
        "Select a group",
        reply_markup=ReplyKeyboardMarkup([[
            KeyboardButton("pick a group", request_chat=request_chat_button),
        ]])
    )


async def on_chat_shared_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"{update.message.chat_shared}", reply_markup=ReplyKeyboardRemove())


def main() -> None:
    application = Application.builder().token("TOKEN").build()

    application.add_handler(CommandHandler("start", on_start))
    application.add_handler(MessageHandler(filters.StatusUpdate.CHAT_SHARED, on_chat_shared_update))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()