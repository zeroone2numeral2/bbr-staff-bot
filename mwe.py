import json
import logging

from telegram import Update, ReplyKeyboardMarkup, KeyboardButtonRequestChat, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ChatMemberHandler

from config import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(update.to_dict())
    print(update.chat_member.via_join_request)


def main() -> None:
    application = Application.builder().token(config.telegram.token).build()

    application.add_handler(ChatMemberHandler(on_chat_member_update, ChatMemberHandler.ANY_CHAT_MEMBER))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
