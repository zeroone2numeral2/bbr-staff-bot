import json
import logging
import re
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update, User as TelegramUser, ChatInviteLink, Bot
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError, BadRequest
from telegram.ext import ContextTypes, CommandHandler
from telegram.ext import filters
from telegram.ext import MessageHandler, CallbackQueryHandler, PrefixHandler, ConversationHandler

from database.models import User, LocalizedText, PrivateChatMessage, Chat
from database.queries import texts, settings, users, chats, private_chat_messages
import decorators
import utilities
from constants import Group, BotSettingKey, Language, LocalizedTextKey
from emojis import Emoji

logger = logging.getLogger(__name__)


def accepted_or_rejected_text(request_id: int, approved: bool, admin: TelegramUser, user: User):
    result = f"{Emoji.GREEN} #APPROVATA" if approved else f"{Emoji.RED} #RIFIUTATA"
    admin_mention = utilities.mention_escaped(admin)
    return f"Richiesta #id{request_id} {result}\n" \
           f"• admin: {admin_mention} [#admin{admin.id}]\n" \
           f"• utente: {user.mention()} [#user{user.user_id}]"


async def invite_link_reply_markup(session: Session, bot: Bot, user: User) -> Optional[InlineKeyboardMarkup]:
    logger.info("generating invite link...")
    users_chat = chats.get_users_chat(session)

    use_default_invite_link = True
    can_be_revoked = False

    if not users_chat.can_invite_users:
        logger.info("we don't have the permission to invite members in the users chat")
    else:
        try:
            chat_invite_link: ChatInviteLink = await bot.create_chat_invite_link(
                users_chat.chat_id,
                member_limit=1,
                name=f"user {user.user_id}"
            )
            invite_link = chat_invite_link.invite_link

            use_default_invite_link = False
            can_be_revoked = True
        except (TelegramError, BadRequest) as e:
            logger.error(f"error while generating invite link for chat {users_chat.chat_id}: {e}")

    if use_default_invite_link:
        logger.info("using default invite link if set")
        invite_link_setting = settings.get_or_create(session, BotSettingKey.CHAT_INVITE_LINK)
        invite_link = invite_link_setting.value()

        if not invite_link:
            return

    user.last_request.set_invite_link(invite_link, can_be_revoked=can_be_revoked)

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"{Emoji.ALIEN} unisciti al gruppo", url=invite_link)]]
    )

    return reply_markup


async def send_message_to_user(session: Session, bot: Bot, user: User):
    fallback_language = settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    ltext = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.APPLICATION_ACCEPTED,
        Language.IT,
        fallback_language=fallback_language
    )
    text = ltext.value

    reply_markup = await invite_link_reply_markup(session, bot, user)

    logger.info("sending message to user...")
    sent_message = await bot.send_message(user.user_id, text, reply_markup=reply_markup)
    private_chat_messages.save(session, sent_message)

    return sent_message


async def delete_history(session: Session, bot: Bot, user: User):
    # send the rabbit message then delete (it will be less noticeable that messages are being deleted)
    rabbit_file_id = "AgACAgQAAxkBAAIF4WRCV9_H-H1tQHnA2443fXtcVy4iAAKkujEbkmDgUYIhRK-rWlZHAQADAgADeAADLwQ"
    sent_message = await bot.send_photo(user.user_id, rabbit_file_id)

    now = utilities.now()

    messages: List[PrivateChatMessage] = private_chat_messages.get_messages(session, user.user_id)
    for message in messages:
        if not message.can_be_deleted(now):
            continue

        logger.debug(f"deleting message {message.message_id} from chat {user.user_id}")
        await bot.delete_message(user.user_id, message.message_id)
        message.set_revoked(reason="/delhistory command")

    # we need to save it here otherwise it would be deleted with all the other messages
    private_chat_messages.save(session, sent_message)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_reject_or_accept_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User, chat: Chat):
    logger.info(f"reject/accept user button {utilities.log(update)}")

    if not user.can_evaluate_applications and not utilities.is_admin(update.effective_user):
        logger.info("user is not allowed to accept/reject requests")
        await update.callback_query.answer(
            f"Non sei abilitato all'approvazione delle richieste degli utenti",
            show_alert=True,
            cache_time=10
        )
        return

    user_id = int(context.matches[0].group("user_id"))
    # application_id = int(context.matches[0].group("request_id"))
    accepted = context.matches[0].group("action") == "accept"

    user: User = users.get_or_create(session, user_id)
    if not user.pending_request_id:
        await update.callback_query.answer(f"Questo utente non ha alcuna richiesta di ingresso pendente", show_alert=True)
        await update.callback_query.edit_message_reply_markup(reply_markup=None)
        return

    if accepted:
        user.accepted(by_user_id=update.effective_user.id)
    else:
        user.rejected(by_user_id=update.effective_user.id)
    session.commit()

    logger.info("editing staff chat message...")
    evaluation_text = accepted_or_rejected_text(user.last_request.id, accepted, update.effective_user, user)
    edited_staff_message = await context.bot.edit_message_text(
        chat_id=user.last_request.staff_message_chat_id,
        message_id=user.last_request.staff_message_message_id,
        text=f"{user.last_request.staff_message_text_html}\n\n{evaluation_text}",
        reply_markup=None
    )
    user.last_request.update_staff_message(edited_staff_message)

    logger.info("sending log chat message...")
    await context.bot.send_message(
        user.last_request.log_message_chat_id,
        evaluation_text,
        reply_to_message_id=user.last_request.log_message_message_id,
        allow_sending_without_reply=True
    )

    if accepted:
        await send_message_to_user(session, context.bot, user)
    else:
        await delete_history(session, context.bot, user)


HANDLERS = (
    (CallbackQueryHandler(on_reject_or_accept_button, rf"(?P<action>accept|reject):(?P<user_id>\d+):(?P<request_id>\d+)$"), Group.NORMAL),
)
