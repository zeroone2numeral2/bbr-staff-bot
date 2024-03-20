import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, Bot, User as TelegramUser, Message
from telegram.error import TelegramError, BadRequest
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import decorators
import utilities
from constants import Group, TempDataKey
from database.models import User, Chat, ApplicationRequest
from database.queries import users, chats, chat_members, common, application_requests
from ext.filters import ChatFilter
from plugins.applications.staff.common import can_evaluate_applications

logger = logging.getLogger(__name__)


async def unban_user(bot: Bot, session: Session, user: User, only_if_banned=True):
    users_chat_member = chat_members.get_chat_member(session, user.user_id, Chat.is_users_chat)
    if users_chat_member:
        try:
            await bot.unban_chat_member(users_chat_member.chat_id, user.user_id, only_if_banned=only_if_banned)
            logger.debug("user unbanned")
            return True
        except (TelegramError, BadRequest) as e:
            logger.debug(f"error while unbanning member: {e}")
            return False


def get_reset_text(user: User, admin_telegram_user: TelegramUser, add_explanation=False) -> str:
    text = (f"<b>#RESET</b> da parte di {admin_telegram_user.mention_html()} (#admin{admin_telegram_user.id}) per "
            f"{user.mention()} (#id{user.user_id})")
    if add_explanation:
        text += f", potrà riutilizzare il bot per fare richiesta di essere aggiunt* al gruppo"

    return text


async def mark_previous_requests_as_reset(bot: Bot, session: Session, user_id: int):
    logger.info("marking all requests as reset and removing hashtag where needed...")

    requests = application_requests.get_user_requests(session, user_id)

    pendente_str = " • #pendente"
    nojoin_str = " • #nojoin"

    reset_requests_count = 0
    edited_log_messages_count = 0

    request: ApplicationRequest
    for request in requests:
        logger.info(f"marking request {request.id} as reset")
        request.reset = True
        reset_requests_count += 1

        if request.log_message_text_html and (pendente_str in request.log_message_text_html or nojoin_str in request.log_message_text_html):
            logger.info(f"removing hashtags from log message {request.log_message_message_id}...")

            new_log_message_text = request.log_message_text_html.replace(pendente_str, "").replace(nojoin_str, "")
            edited_message = await utilities.edit_text_by_ids_safe(
                bot=bot,
                chat_id=request.log_message_chat_id,
                message_id=request.log_message_message_id,
                text=new_log_message_text
            )
            if edited_message:
                request.update_log_chat_message(edited_message)
                edited_log_messages_count += 1

    logger.info(f"requests reset: {reset_requests_count}; edited log messages: {edited_log_messages_count}")


@decorators.catch_exception()
@decorators.pass_session()
async def on_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/reset {utilities.log(update)}")

    if not can_evaluate_applications(session, update.effective_user):
        logger.info("user is not allowed to use this command")
        return

    user: User = await common.get_user_instance_from_message(update, context, session)
    if not user:
        # the function will take care of sending the error message too
        return

    user.reset_evaluation()
    # do not answer in the group. it will be sent in the log channel and auto-forwarded in the group
    # await update.message.reply_text(
    #     f"{user.mention()} ora potrà richiedere nuovamente di essere ammesso al gruppo "
    #     f"(eventuali richieste pendenti o rifiutate sono state dimenticate, se era bannato è stato sbannato)",
    #     do_quote=True
    # )

    # unban the user so they can join again, just in case the user was removed manually before /reset was used
    only_if_banned = not utilities.get_command(update.message.text) == "resetkick"  # check whether to kick the user
    await unban_user(context.bot, session, user, only_if_banned=only_if_banned)

    log_chat = chats.get_chat(session, Chat.is_log_chat)
    if not log_chat:
        logger.warning("no log chat set")
        return

    log_text = get_reset_text(user, update.effective_user)

    additional_context = utilities.get_argument(
        ["resetkick", "reset"],
        update.message.text_html,
        bot_username=context.bot.username,
        remove_user_id_hashtag=True
    )
    if additional_context:
        log_text += f"\n<b>Contesto</b>: {additional_context}"

        # send the context to the user
        # sent_message = await context.bot.send_message(user.user_id, additional_context)
        # private_chat_messages.save(session, sent_message)

    await context.bot.send_message(log_chat.chat_id, log_text)

    # marks all previous requests as reset, and will remove the #pendente/#nojoin hashtags
    session.commit()  # make sure to commit before executing this function
    await mark_previous_requests_as_reset(context.bot, session, user.user_id)


@decorators.catch_exception()
@decorators.pass_session()
async def on_reset_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"reset button {utilities.log(update)}")

    if not can_evaluate_applications(session, update.effective_user):
        logger.info("user is not allowed to accept/reject requests")
        await update.callback_query.answer(
            f"Non puoi gestire le richieste degli utenti",
            show_alert=True,
            cache_time=10
        )
        return

    user_id = int(context.matches[0].group("user_id"))
    request_id = int(context.matches[0].group("request_id"))

    tap_key = f"request:reset:{update.effective_message.message_id}"
    if TempDataKey.EVALUATION_BUTTONS_ONCE not in context.user_data:
        context.user_data[TempDataKey.EVALUATION_BUTTONS_ONCE] = {}
    if not context.user_data[TempDataKey.EVALUATION_BUTTONS_ONCE].pop(tap_key, False):
        logger.info(f"first button tap for <reset> ({tap_key})")
        context.user_data[TempDataKey.EVALUATION_BUTTONS_ONCE][tap_key] = True
        await update.callback_query.answer(f"Usa di nuovo il tasto per confermare. L'utente potrà riprovare ad effettuare la richiesta usando /start", show_alert=True)
        return

    user: User = users.get_or_create(session, user_id)
    if not user.pending_request_id and not user.last_request_id:
        logger.info(f"user {user.user_id} has no completed/pending request")
        await update.callback_query.answer(f"Questo utente non ha alcuna richiesta di ingresso pendente/conclusa da resettare. Può già usare /start",
                                           show_alert=True, cache_time=10)
        await utilities.delete_or_remove_markup_safe(update.effective_message)
        return

    await unban_user(context.bot, session, user, only_if_banned=True)

    # reset all evaluations (pending/completed)...
    logger.info(f"resetting completed/pending requests for user {user.user_id}...")
    user.reset_evaluation()

    # ...but we retrieve the request where the reset button was used, so we can save the new edited staff message
    request: Optional[ApplicationRequest] = application_requests.get_by_id(session, request_id)
    logger.info(f"request_id: {request.id}")

    logger.info("editing log message...")
    # the #pendente and #nojoin hashtags will be removed later, by mark_previous_requests_as_reset()
    new_log_message_text = f"{request.log_message_text_html}\n\n{get_reset_text(user, update.effective_user)}"
    edited_log_message: Message = await context.bot.edit_message_text(
        chat_id=request.log_message_chat_id,
        message_id=request.log_message_message_id,
        text=new_log_message_text
    )
    request.update_log_chat_message(edited_log_message)
    session.commit()  # make sure to commit now, because we will loop through the log messages later, to remove the hashtags

    logger.info("editing evaluation buttons message...")
    edited_evaluation_buttons_message = await context.bot.edit_message_text(
        chat_id=request.evaluation_buttons_message_chat_id,
        message_id=request.evaluation_buttons_message_message_id,
        text=get_reset_text(user, update.effective_user, add_explanation=True),
        reply_markup=None
    )
    request.update_evaluation_buttons_message(edited_evaluation_buttons_message)

    # marks all previous requests as reset, and will remove the #pendente/#nojoin hashtags
    session.commit()  # make sure to commit before executing this function
    await mark_previous_requests_as_reset(context.bot, session, user.user_id)


HANDLERS = (
    (CommandHandler(["reset", "resetkick"], on_reset_command, ChatFilter.EVALUATION), Group.NORMAL),
    (CallbackQueryHandler(on_reset_button, rf"(?P<action>reset):(?P<user_id>\d+):(?P<request_id>\d+)$"), Group.NORMAL),
)
