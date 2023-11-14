import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext import filters

import decorators
import utilities
from constants import BotSettingKey, LocalizedTextKey, Group, Language
from database.models import User, UserMessage, Chat, ChatMember as DbChatMember
from database.queries import settings, chats, texts, private_chat_messages, chat_members

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_ban()
async def on_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"new user message {utilities.log(update)}")

    if utilities.is_superadmin(update.effective_user):
        logger.info("ignoring user message: superadmin")
        # TODO: continue update propagation
        return

    if chat_members.is_member(session, update.effective_user.id, Chat.is_staff_chat):
        logger.info("ignoring user message: staff chat member")
        # TODO: continue update propagation
        return

    target_chat: Chat = chats.get_chat(session, Chat.is_staff_chat)  # we check whether none or not later

    if user.conversate_with_staff_override:
        # in this case, the user should be able to talk to the staff even if a request is pending/rejected
        # if the user has a pending/rejected request, use the evaluation chat as target chat
        # otherwise, keep the staff chat as target chat
        logger.info("user can talk to the staff regardless of the approval mode status/whether they are part of the users chat or not")
        if user.pending_request_id or user.last_request.rejected():
            logger.info("user has a pending/rejected request: target chat is evaluation chat")
            target_chat: Chat = chats.get_chat(session, Chat.is_evaluation_chat)
    else:
        approval_mode = settings.get_or_create(session, BotSettingKey.APPROVAL_MODE).value()
        if approval_mode:
            # if approval mode is on and conversate_with_staff_override is false, find all possible
            # cases where we should ignore the message
            logger.debug("approval mode is on and conversate_with_staff_override is false")

            accept_message = False

            if not accept_message and (user.last_request and user.last_request.accepted()):
                logger.info("allowed: user's last request was accepted")
                accept_message = True

            if not accept_message:
                # do this check only if needed
                chat_member = chat_members.get_chat_member(session, update.effective_user.id, Chat.is_users_chat)
                if not chat_member:
                    # we don't have the ChatMember record saved for this user in the users chat
                    users_chat = chats.get_chat(session, Chat.is_users_chat)
                    logger.info(f"no ChatMember record for user {update.effective_user.id} in chat {users_chat.chat_id}, fetching ChatMember...")
                    tg_chat_member = await context.bot.get_chat_member(users_chat.chat_id, update.effective_user.id)
                    chat_member = DbChatMember.from_chat_member(users_chat.chat_id, tg_chat_member)
                    session.add(chat_member)
                    session.commit()

                if not accept_message and chat_member.is_member():
                    logger.info("allowed: user is a meber of the users chat, or was a member or left")
                    accept_message = True

                if not accept_message and chat_member.left_or_kicked():
                    logger.info("allowed: user was a member of the users chat and left (or was kicked)")
                    accept_message = True

            if not accept_message:
                logger.info("ignoring user message: none of the requirements were met")

                if user.last_request and user.last_request.rejected():
                    logger.info(f"user's last request was rejected: we will answer if the ltext is set")
                    ltext = texts.get_localized_text_with_fallback(
                        session,
                        LocalizedTextKey.APPLICATION_REJECTED_ANSWER,
                        Language.IT,
                        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value(),
                        raise_if_no_fallback=False
                    )
                    if ltext:
                        logger.info("sending APPLICATION_REJECTED_ANSWER message...")
                        sent_message = await update.message.reply_html(ltext.value)
                        private_chat_messages.save(session, sent_message)
                return

    if not target_chat:
        logger.warning("ignoring user message: there is no target chat set")
        return

    logger.debug("forwarding to staff...")
    forwarded_message = await update.message.forward(target_chat.chat_id)
    user_message = UserMessage(
        message_id=update.message.message_id,
        user_id=update.effective_user.id,
        forwarded_chat_id=target_chat.chat_id,
        forwarded_message_id=forwarded_message.message_id,
        message_datetime=update.effective_message.date
    )
    user_message.save_message_json(forwarded_message)
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
    (MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, on_user_message), Group.NORMAL),
)
