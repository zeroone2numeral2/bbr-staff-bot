import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext import filters

from database.models import User, UserMessage, Chat
from database.queries import settings, chats, texts, private_chat_messages
import decorators
import utilities
from constants import BotSettingKey, LocalizedTextKey, Group, Language
from emojis import Emoji
from ext.filters import Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"new user message {utilities.log(update)}")

    if user.banned:
        logger.info(f"ignoring user message because the user was banned (shadowban: {user.shadowban})")
        if not user.shadowban:
            reason = user.banned_reason or "not provided"
            sent_message = await update.message.reply_text(f"{Emoji.BANNED} You were banned from using this bot. Reason: {utilities.escape_html(reason)}")
            private_chat_messages.save(session, sent_message)
        return

    chat: Chat = chats.get_staff_chat(session)
    if not chat:
        logger.warning("ignoring message: there is no staff chat set")
        return

    approval_mode = settings.get_or_create(session, BotSettingKey.APPROVAL_MODE).value()

    if approval_mode and user.pending_request_id:
        logger.info("user has a pending request: ignoring message")
        return

    if approval_mode and user.last_request and user.last_request.status is False:
        logger.info(f"ignoring user message because they were rejected")
        ltext = texts.get_localized_text_with_fallback(
            session,
            LocalizedTextKey.APPLICATION_REJECTED_ANSWER,
            Language.IT,
            fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value(),
            raise_if_no_fallback=False
        )
        if ltext:
            sent_message = await update.message.reply_html(ltext.value)
            private_chat_messages.save(session, sent_message)
        return

    forwarded_message = await update.message.forward(chat.chat_id)
    user_message = UserMessage(
        message_id=update.message.message_id,
        user_id=update.effective_user.id,
        forwarded_chat_id=chat.chat_id,
        forwarded_message_id=forwarded_message.message_id,
        message_datetime=update.effective_message.date
    )
    session.add(user_message)

    if settings.get_or_create(session, BotSettingKey.SENT_TO_STAFF).value():
        user_language = utilities.get_language_code(user.selected_language, update.effective_user.language_code)
        logger.info(f"sending 'sent to staff' message (user language: {user_language})...")
        try:
            sent_to_staff = texts.get_localized_text_with_fallback(
                session,
                LocalizedTextKey.SENT_TO_STAFF,
                user_language,
                fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value(),
                raise_if_no_fallback=True
            )
            text = sent_to_staff.value
        except ValueError as e:
            logger.error(f"{e}")
            text = "<i>delivered</i>"

        sent_message = await update.message.reply_text(text, quote=True)
        private_chat_messages.save(session, sent_message)

    user.set_started()
    user.update_last_message()


HANDLERS = (
    (MessageHandler(filters.ChatType.PRIVATE & ~Filter.SUPERADMIN, on_user_message), Group.NORMAL),
)
