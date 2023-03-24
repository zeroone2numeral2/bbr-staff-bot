import logging
from typing import Optional

import pytz
from sqlalchemy.orm import Session
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Defaults, filters, MessageHandler
from telegram.ext.filters import MessageFilter

from database.models import User, UserMessage
import decorators
import utilities
from emojis import Emoji
from config import config

logger = logging.getLogger(__name__)

defaults = Defaults(
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        tzinfo=pytz.timezone('Europe/Rome')
    )
bot = ApplicationBuilder().token(config.telegram.token).defaults(defaults).build()


class FilterReplyToBot(MessageFilter):
    def filter(self, message):
        if message.reply_to_message and message.reply_to_message.from_user:
            return message.reply_to_message.from_user.id == bot.bot.id


filter_reply_to_bot = FilterReplyToBot()


@decorators.pass_session(pass_user=True)
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    await update.message.reply_html("Hi :)")
    user.set_started(update_last_message=True)


@decorators.pass_session(pass_user=True)
async def on_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    if user.banned:
        reason = user.banned_reason or "-"
        await update.message.reply_text(f"{Emoji.BANNED} You were banned from using this bot. Reason: {utilities.escape_html(reason)}")
        return

    forwarded_message = await update.message.forward(config.staff.chat_id)
    user_message = UserMessage(
        message_id=update.message.message_id,
        user_id=update.effective_user.id,
        forwarded_chat_id=config.staff.chat_id,
        forwarded_message_id=forwarded_message.message_id
    )
    session.add(user_message)
    user.set_started(update_last_message=True)


async def on_chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{update.effective_chat.id}")


@decorators.pass_session()
async def on_bot_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"reply to a bot message in {update.effective_chat.title} ({update.effective_chat.id})")

    chat_id = update.effective_chat.id
    replied_to_message_id = update.message.reply_to_message.message_id

    user_message: UserMessage = session.query(UserMessage).filter(
        UserMessage.forwarded_chat_id == chat_id,
        UserMessage.forwarded_message_id == replied_to_message_id
    ).one_or_none()

    if not user_message:
        logger.warning(f"couldn't find replied-to message, chat_id: {chat_id}; message_id: {replied_to_message_id}")
        return

    await bot.bot.send_message(
        chat_id=user_message.user_id,
        text=update.message.text,
        reply_to_message_id=user_message.message_id
    )

    user_message.add_reply()


def main():
    utilities.load_logging_config('logging.json')

    bot.add_handler(CommandHandler('start', on_start_command, filters.ChatType.PRIVATE))
    bot.add_handler(MessageHandler(filters.ChatType.PRIVATE, on_user_message))
    bot.add_handler(CommandHandler('chatid', on_chatid_command, filters.ChatType.GROUPS))
    bot.add_handler(MessageHandler(filters.ChatType.GROUPS & filter_reply_to_bot, on_bot_message_reply))

    bot.run_polling(
        drop_pending_updates=False,
        allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY, Update.CHAT_MEMBER, Update.MY_CHAT_MEMBER]
    )


if __name__ == '__main__':
    main()
