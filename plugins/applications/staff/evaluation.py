import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, User as TelegramUser, ChatInviteLink, Bot
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError, BadRequest
from telegram.ext import ContextTypes
from telegram.ext import filters
from telegram.ext import MessageHandler, CallbackQueryHandler, PrefixHandler, ConversationHandler

from database.models import User, LocalizedText
from database.queries import texts, settings, users, chats
import decorators
import utilities
from constants import COMMAND_PREFIXES, State, TempDataKey, CONVERSATION_TIMEOUT, Action, \
    LOCALIZED_TEXTS_DESCRIPTORS, LANGUAGES, ACTION_DESCRIPTORS, Group, BotSettingKey, Language, LocalizedTextKey
from emojis import Emoji
from replacements import replace_placeholders

logger = logging.getLogger(__name__)


def approved_or_rejected_text(request_id: int, approved: bool, user: TelegramUser):
    result = "#APPROVATA" if approved else "#RIFIUTATA"
    return f"Richiesta #id{request_id} {result} da {user.mention_html()} (#admin{user.id})"


def invite_link_reply_markup(session: Session, bot: Bot, user: User) -> Optional[InlineKeyboardMarkup]:
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


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.staff_admin()
async def on_accept_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"accept user button {utilities.log(update)}")

    user_id = int(context.matches[0].group("user_id"))
    # application_id = int(context.matches[0].group("request_id"))

    user: User = users.get_or_create(session, user_id)
    if not user.pending_request_id:
        await update.callback_query.answer(f"Questo utente non ha alcuna richiesta di ingresso pendente", show_alert=True)
        await update.callback_query.edit_message_reply_markup(reply_markup=None)
        return

    user.accepted(update.effective_user.id)
    session.commit()

    fallback_language = settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    ltext = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.APPLICATION_ACCEPTED,
        Language.IT,
        fallback_language=fallback_language
    )
    text = replace_placeholders(ltext.value, update.effective_user, session)

    reply_markup = invite_link_reply_markup(session, context.bot, user)

    logger.info("sending message to user...")
    await context.bot.send_message(user_id, text, reply_markup=reply_markup)

    logger.info("editing staff chat message...")
    evaluation_text = approved_or_rejected_text(user.last_request.id, True, update.effective_user)
    await context.bot.edit_message_text(
        chat_id=user.last_request.staff_message_chat_id,
        message_id=user.last_request.staff_message_message_id,
        text=f"{user.last_request.staff_message_text_html}\n\n{evaluation_text}",
        reply_markup=None
    )

    logger.info("sending log chat message...")
    await context.bot.send_message(
        user.last_request.log_message_chat_id,
        evaluation_text,
        reply_to_message_id=user.last_request.log_message_message_id,
        allow_sending_without_reply=True
    )


HANDLERS = (
    (CallbackQueryHandler(on_accept_button, rf"accept:(?P<user_id>\d+):(?P<request_id>\d+)$"), Group.NORMAL),
)
