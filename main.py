import logging

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

import utilities
from config import config

logger = logging.getLogger(__name__)


def main():
    utilities.load_logging_config('logging.json')

    bot = ApplicationBuilder().token(config.telegram.token).build()

    # start_handler = CommandHandler('start', start)
    # bot.add_handler(start_handler)

    bot.run_polling(
        drop_pending_updates=False,
        allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY, Update.CHAT_MEMBER, Update.MY_CHAT_MEMBER]
    )


if __name__ == '__main__':
    main()
