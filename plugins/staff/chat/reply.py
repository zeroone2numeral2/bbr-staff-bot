import logging
import re
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, MessageId
from telegram.constants import ChatAction
from telegram.error import TelegramError, BadRequest
from telegram.ext import filters, ContextTypes, MessageHandler
from telegram.ext.filters import MessageFilter

from constants import Group
from database.models import UserMessage, AdminMessage, User, Chat
from database.queries import user_messages, admin_messages, users
import decorators
import utilities
from emojis import Emoji
from ext.filters import ChatFilter
from config import config

logger = logging.getLogger(__name__)


class FilterReplyTopicsAware(MessageFilter):
    def filter(self, message):
        if message.reply_to_message and message.reply_to_message.forum_topic_created:
            return False

        return bool(message.reply_to_message)


reply_topics_aware = FilterReplyTopicsAware()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_admin_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User, chat: Chat):
    logger.info(f"reply to a message starting by ++ {utilities.log(update)}")

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
        reply_to_message_id=admin_message.reply_message_id,  # reply to the admin message we previously sent in the chat
        allow_sending_without_reply=True,
        protect_content=config.settings.protected_admin_replies
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

    admin_message.save_message_json(sent_message)
    admin_message.user_message.add_reply()

    await update.message.reply_html("<i>message sent to the user</i>", quote=True)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"reply to a message {utilities.log(update)}")

    if update.message.reply_to_message.from_user and update.message.reply_to_message.from_user.id != context.bot.id:
        logger.debug("reply to a non-bot message: ignoring")
        return

    text = update.message.text or update.message.caption
    if text and text.startswith("."):
        logger.info("ignoring staff reply starting by .")
        return

    user_message: Optional[UserMessage] = None
    if chat.is_evaluation_chat and update.message.reply_to_message.text and update.message.reply_to_message.text.startswith("nuova #richiesta"):
        logger.info("reply to an user request message sent by the bot in the evaluation chat")
        # get the User object from the db based on the #id hashtag
        user_id = utilities.get_user_id_from_text(update.message.reply_to_message.text)
        user: User = users.get_or_create(session, user_id, create_if_missing=False)
        if not user:
            # return if missing
            logger.warning(f"couldn't find user {user_id} in the database")
            return

        # set this flag to true so we know that the user's replies should be forwarded to the staff
        user.conversate_with_staff_override = True
    else:
        user_message: UserMessage = user_messages.get_user_message(session, update)
        if not user_message:
            logger.warning(f"couldn't find replied-to message, "
                           f"chat_id: {update.effective_chat.id}; "
                           f"message_id: {update.message.reply_to_message.message_id}")
            return
        user: User = user_message.user

    try:
        await context.bot.send_chat_action(user.user_id, ChatAction.TYPING)
        # time.sleep(3)
    except (TelegramError, BadRequest) as e:
        if e.message.lower() == "forbidden: bot was blocked by the user":
            logger.warning("bot was blocked by the user")
            await update.message.reply_text(
                f"{Emoji.WARNING} <i>coudln't send the message to the user: they blocked the bot</i>",
                quote=True
            )
            user.set_stopped()
            return
        else:
            raise e

    # if the admin message is a reply to a request message in the evaluation chat, reply to the message we sent the user
    # when we told them their request was sent to the staff
    user_chat_reply_to_message_id = user_message.message_id if user_message else user.pending_request.request_sent_message_message_id
    sent_message: MessageId = await update.message.copy(
        chat_id=user.user_id,
        reply_to_message_id=user_chat_reply_to_message_id,
        allow_sending_without_reply=True,  # in case the user deleted their own message in the bot's chat
        protect_content=config.settings.protected_admin_replies
    )

    if user_message:
        user_message.add_reply()
    session.commit()

    admin_message = AdminMessage(
        message_id=update.effective_message.id,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        user_message_id=user_chat_reply_to_message_id,  # the message_id of the message we replied to in ther user chat
        reply_message_id=sent_message.message_id,
        message_datetime=update.effective_message.date
    )
    session.add(admin_message)

    await update.message.reply_html("<i>message sent to the user</i>", quote=True)


HANDLERS = (
    (MessageHandler((ChatFilter.STAFF | ChatFilter.EVALUATION) & ~filters.UpdateType.EDITED_MESSAGE & reply_topics_aware & filters.Regex(r"^\+\+\s*.+"), on_admin_message_reply), Group.NORMAL),
    (MessageHandler((ChatFilter.STAFF | ChatFilter.EVALUATION) & ~filters.UpdateType.EDITED_MESSAGE & reply_topics_aware, on_message_reply), Group.NORMAL),
)
