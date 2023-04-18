import logging
import re

from sqlalchemy.orm import Session
from telegram import Update
from telegram.constants import ChatAction
from telegram.error import TelegramError, BadRequest
from telegram.ext import filters, ContextTypes, MessageHandler
from telegram.ext.filters import MessageFilter

from constants import Group
from database.models import UserMessage, AdminMessage, User
from database.queries import user_messages, admin_messages
import decorators
import utilities
from emojis import Emoji

logger = logging.getLogger(__name__)


class FilterReplyTopicsAware(MessageFilter):
    def filter(self, message):
        if message.reply_to_message and message.reply_to_message.forum_topic_created:
            return False

        return bool(message.reply_to_message)


reply_topics_aware = FilterReplyTopicsAware()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_admin_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"reply to an admin message starting by ++ {utilities.log(update)}")

    if update.message.reply_to_message.from_user.id == context.bot.id:
        await update.message.reply_text("⚠️ <i>please reply to the admin message you want "
                                        "to reply to</i>")
        return

    admin_message: AdminMessage = admin_messages.get_admin_message(session, update)
    if not admin_message:
        logger.warning(f"couldn't find replied-to admin message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        await update.message.reply_text(
            "⚠️ <i>can't find the message to reply to in the database</i>",
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        return

    await context.bot.send_chat_action(admin_message.user_message.user_id, ChatAction.TYPING)
    # time.sleep(3)

    sent_message = await context.bot.send_message(
        chat_id=admin_message.user_message.user_id,
        text=re.sub(r"^\+\+\s*", "", update.effective_message.text_html),
        reply_to_message_id=admin_message.reply_message_id  # reply to the admin message we previously sent in the chat
    )

    admin_message = AdminMessage(
        message_id=update.effective_message.id,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,  # admin's user_id
        user_message_id=admin_message.user_message.message_id,  # root user message that generated the admins' replies chain
        reply_message_id=sent_message.message_id,
        message_datetime=update.effective_message.date
    )
    session.add(admin_message)
    session.commit()  # we need to commit now because otherwise 'admin_message.user_message' would be none

    admin_message.user_message.add_reply()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_bot_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"reply to a message {utilities.log(update)}")

    if not update.message.reply_to_message.from_user and update.message.reply_to_message.from_user.id == context.bot.id:
        await update.effective_message.reply_text("<i>Reply to an user's message</i>")
        return

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    try:
        await context.bot.send_chat_action(user_message.user_id, ChatAction.TYPING)
        # time.sleep(3)
    except (TelegramError, BadRequest) as e:
        if e.message.lower() == "forbidden: bot was blocked by the user":
            logger.warning("bot was blocked by the user")
            await update.message.reply_text(
                f"{Emoji.WARNING} <i>coudln't send the message to the user: they blocked the bot</i>",
                quote=True
            )
            user_message.user.set_stopped()
            return
        else:
            raise e

    sent_message = await update.message.copy(
        chat_id=user_message.user_id,
        reply_to_message_id=user_message.message_id
    )

    user_message.add_reply()
    session.commit()

    admin_message = AdminMessage(
        message_id=update.effective_message.id,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        user_message_id=user_message.message_id,
        reply_message_id=sent_message.message_id,
        message_datetime=update.effective_message.date
    )
    session.add(admin_message)


HANDLERS = (
    (MessageHandler(filters.ChatType.GROUPS & reply_topics_aware & filters.Regex(r"^\+\+\s*.+"), on_admin_message_reply), Group.NORMAL),
    (MessageHandler(filters.ChatType.GROUPS & reply_topics_aware, on_bot_message_reply), Group.NORMAL),
)
