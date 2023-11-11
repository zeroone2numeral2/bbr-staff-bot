import logging
import re
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram import Update, User as TelegramUser, ChatInviteLink, Bot
from telegram.error import TelegramError, BadRequest
from telegram.ext import CallbackQueryHandler, PrefixHandler
from telegram.ext import ContextTypes
from telegram.ext import filters

import decorators
import utilities
from config import config
from constants import Group, BotSettingKey, Language, LocalizedTextKey, COMMAND_PREFIXES, TempDataKey
from database.models import User, PrivateChatMessage, Chat, BotSetting
from database.queries import texts, settings, users, chats, private_chat_messages, chat_members
from emojis import Emoji
from ext.filters import ChatFilter
from plugins.applications.staff.common import can_evaluate_applications

logger = logging.getLogger(__name__)


def accepted_or_rejected_text(request_id: int, approved: bool, admin: TelegramUser, user: User):
    result = f"{Emoji.GREEN} #APPROVATA" if approved else f"{Emoji.RED} #RIFIUTATA"
    admin_mention = utilities.mention_escaped(admin)
    return f"<b>Richiesta #rid{request_id} {result}</b>\n" \
           f"admin: {admin_mention} • #admin{admin.id}\n" \
           f"utente: {user.mention()} • #id{user.user_id}"


async def invite_link_reply_markup(session: Session, bot: Bot, user: User) -> Optional[InlineKeyboardMarkup]:
    logger.info("generating invite link...")
    users_chat = chats.get_chat(session, Chat.is_users_chat)

    use_default_invite_link = True  # we set this to False if the invite link generation succeeds
    can_be_revoked = False

    if not users_chat.can_invite_users:
        logger.info("we don't have the permission to generate invite links for the users chat")
    else:
        # try to generate a one-time invite link
        # if we fail, use the default one
        try:
            chat_invite_link: ChatInviteLink = await bot.create_chat_invite_link(
                users_chat.chat_id,
                member_limit=1,
                name=f"user {user.user_id}",
                creates_join_request=config.settings.invite_link_join_request
            )
            invite_link = chat_invite_link.invite_link

            use_default_invite_link = False
            can_be_revoked = True
        except (TelegramError, BadRequest) as e:
            logger.error(f"error while generating invite link for chat {users_chat.chat_id}: {e}")

    if use_default_invite_link:
        logger.info("using default invite link (if set)")
        invite_link_setting = settings.get_or_create(session, BotSettingKey.CHAT_INVITE_LINK)
        invite_link = invite_link_setting.value()

        if not invite_link:
            logger.warning("user will receive no invite link because we failed to generate one and no primary link is set")
            return  # reply_markup will be None

    # noinspection PyUnboundLocalVariable
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
    sent_message = await bot.send_message(user.user_id, text, reply_markup=reply_markup, protect_content=True)
    private_chat_messages.save(session, sent_message)
    user.last_request.accepted_message_message_id = sent_message.message_id

    return sent_message


async def delete_history(session: Session, bot: Bot, user: User, delete_reason: str, send_rabbit=True):
    sent_rabbit_message = None
    if send_rabbit:
        # send the rabbit message then delete (it will be less noticeable that messages are being deleted)
        # rabbit_file_id = "AgACAgQAAxkBAAIF4WRCV9_H-H1tQHnA2443fXtcVy4iAAKkujEbkmDgUYIhRK-rWlZHAQADAgADeAADLwQ"
        setting: BotSetting = settings.get_or_create(session, BotSettingKey.RABBIT_FILE)

        if setting.value():
            logger.info("sending rabbit file...")
            try:
                sent_rabbit_message = await bot.send_photo(user.user_id, setting.value(), protect_content=True)
            except BadRequest as e:
                if "wrong file identifier/http url specified" in e.message.lower():
                    logger.error(f"cannot send file: {e.message}")
                else:
                    raise e

    now = utilities.now()

    result = dict(deleted=0, too_old=0, failed=0)

    messages: List[PrivateChatMessage] = private_chat_messages.get_messages(session, user.user_id)
    for message in messages:
        if message.revoked:
            continue

        if not message.can_be_deleted(now):
            result["too_old"] += 1
            continue

        logger.debug(f"deleting message {message.message_id} from chat {user.user_id}...")
        success, _ = await utilities.delete_messages_by_id_safe(bot, user.user_id, message.message_id)
        logger.debug(f"...success: {success}")
        message.set_revoked(reason=delete_reason)

        if not success:
            result["failed"] += 1
        else:
            result["deleted"] += 1

    # we need to save it here after we're done with the cleanup, otherwise it would be deleted with all the other messages
    if sent_rabbit_message:
        # sending the gif might have failed
        private_chat_messages.save(session, sent_rabbit_message)

    return result


async def accept_or_reject(session: Session, bot: Bot, user: User, accepted: bool, admin: TelegramUser, delete_history_if_rejected=True):
    if accepted:
        user.accept(by_user_id=admin.id)
    else:
        user.reject(by_user_id=admin.id)
    session.commit()

    logger.info("editing evaluation chat message and removing keyboard...")
    # we attach it at the end of the original message
    evaluation_text = accepted_or_rejected_text(user.last_request.id, accepted, admin, user)
    # we have to remove the #pendente hashtag
    original_message_without_pending_hashtag = user.last_request.staff_message_text_html.replace(" • #pendente", "")
    edited_staff_message = await bot.edit_message_text(
        chat_id=user.last_request.staff_message_chat_id,
        message_id=user.last_request.staff_message_message_id,
        text=f"{original_message_without_pending_hashtag}\n\n{evaluation_text}",
        reply_markup=None
    )
    user.last_request.update_staff_chat_message(edited_staff_message)

    logger.info("sending new accepted/rejected log chat message...")
    await bot.send_message(
        user.last_request.log_message_chat_id,
        evaluation_text,
        reply_to_message_id=user.last_request.log_message_message_id,
        allow_sending_without_reply=True
    )

    logger.info("editing previously sent log chat message...")  # we only need to remove the #pendente hashtag
    edited_log_chat_message = await bot.edit_message_text(
        chat_id=user.last_request.log_message_chat_id,
        message_id=user.last_request.log_message_message_id,
        text=f"{user.last_request.log_message_text_html.replace(' • #pendente', '')}",
        reply_markup=None
    )
    user.last_request.update_log_chat_message(edited_log_chat_message)

    if accepted:
        await send_message_to_user(session, bot, user)
    elif not accepted and delete_history_if_rejected:
        # make sure to only enter here if 'accepted' is false
        logger.info("deleting history...")
        await delete_history(session, bot, user, delete_reason="user was rejected")


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_reject_or_accept_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User, chat: Chat):
    logger.info(f"reject/accept user button {utilities.log(update)}")

    if not can_evaluate_applications(session, update.effective_user):
        logger.info("user is not allowed to accept/reject requests")
        await update.callback_query.answer(
            f"Non puoi gestire le richieste degli utenti",
            show_alert=True,
            cache_time=10
        )
        return

    user_id = int(context.matches[0].group("user_id"))
    action = context.matches[0].group("action")
    # application_id = int(context.matches[0].group("request_id"))

    tap_key = f"request:{action}:{update.effective_message.message_id}"
    if TempDataKey.EVALUATION_BUTTONS_ONCE not in context.user_data:
        context.user_data[TempDataKey.EVALUATION_BUTTONS_ONCE] = {}
    if not context.user_data[TempDataKey.EVALUATION_BUTTONS_ONCE].pop(tap_key, False):
        logger.info(f"first button tap for <{action}>")
        context.user_data[TempDataKey.EVALUATION_BUTTONS_ONCE][tap_key] = True
        await update.callback_query.answer(f"usa di nuov il tasto per confermare")
        return

    accepted = action == "accept"

    user: User = users.get_or_create(session, user_id)
    if not user.pending_request_id:
        logger.info(f"user {user.user_id} has no pending request")
        await update.callback_query.answer(f"Questo utente non ha alcuna richiesta di ingresso pendente", show_alert=True)
        await update.callback_query.edit_message_reply_markup(reply_markup=None)
        return

    await accept_or_reject(
        session=session,
        bot=context.bot,
        user=user,
        accepted=accepted,
        admin=update.effective_user
    )


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_reject_or_accept_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User, chat: Chat):
    logger.info(f"/accetta or /rifiuta command {utilities.log(update)}")

    if not can_evaluate_applications(session, update.effective_user):
        logger.info("user is not allowed to accept/reject requests")
        await update.message.reply_text(f"Non puoi gestire le richieste degli utenti")
        return

    user_id = utilities.get_user_id_from_text(update.message.reply_to_message.text)
    if not user_id:
        await update.message.reply_text(f"<i>impossibile rilevare hashtag con ID dell'utente</i>", quote=True)
        return

    logger.info(f"user_id: {user_id}")
    user: User = users.get_or_create(session, user_id)
    if not user.pending_request_id:
        await update.message.reply_text(f"Questo utente non ha alcuna richiesta di ingresso pendente")
        return

    accepted = bool(re.search(r"^/accetta", update.message.text, re.I))

    delete_history_if_rejected = True
    if context.args and "nodel" in context.args:
        logger.info("skipping history delete")
        delete_history_if_rejected=False

    await accept_or_reject(
        session=session,
        bot=context.bot,
        user=user,
        accepted=accepted,
        admin=update.effective_user,
        delete_history_if_rejected=delete_history_if_rejected
    )

    await update.message.reply_text(
        f"<i>fatto! {user.last_request.staff_message_link('vai alla richiesta')}</i>",
        quote=True
    )


@decorators.catch_exception()
@decorators.pass_session()
async def on_delhistory_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/delhistory command {utilities.log(update)}")

    text = update.message.reply_to_message.text if update.message.reply_to_message else update.message.text

    user_id = utilities.get_user_id_from_text(text)
    if not user_id:
        await update.message.reply_text(f"<i>impossibile rilevare hashtag con ID dell'utente</i>", quote=True)
        return

    logger.info(f"user_id: {user_id}")
    user: User = users.get_or_create(session, user_id)

    send_rabbit = False
    if context.args and context.args[0].lower() == "rabbit":
        send_rabbit = True

    await update.message.reply_html(f"Elimino la cronologia dei messaggi per {user.mention()}...", quote=True)

    result_dict = await delete_history(session, context.bot, user, delete_reason="/delhistory", send_rabbit=send_rabbit)

    await update.message.reply_text(
        f"• eliminati: {result_dict['deleted']}\n"
        f"• non eliminati perchè troppo vecchi: {result_dict['too_old']}\n"
        f"• non eliminati per altri motivi: {result_dict['failed']}\n"
        f"• file rabbit: {'inviato (se impostato)' if send_rabbit else 'non inviato'}",
        quote=True
    )


HANDLERS = (
    (CallbackQueryHandler(on_reject_or_accept_button, rf"(?P<action>accept|reject):(?P<user_id>\d+):(?P<request_id>\d+)$"), Group.NORMAL),
    (PrefixHandler(COMMAND_PREFIXES, ["accetta", "rifiuta"], on_reject_or_accept_command, filters.REPLY & ChatFilter.EVALUATION), Group.NORMAL),
    (PrefixHandler(COMMAND_PREFIXES, ["delhistory"], on_delhistory_command, ChatFilter.EVALUATION), Group.NORMAL),
)
