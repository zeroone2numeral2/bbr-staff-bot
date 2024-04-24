import logging
import re
import sqlite3
from typing import Optional, List

import sqlalchemy
from sqlalchemy.orm import Session
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Bot, Message
from telegram.constants import MessageLimit, MediaGroupLimit
from telegram.ext import CommandHandler, CallbackQueryHandler
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, \
    CallbackContext
from telegram.ext import filters

import decorators
import utilities
from constants import BotSettingKey, LocalizedTextKey, Group, Language, TempDataKey, Timeout
from database.base import session_scope
from database.models import User, ChatMember as DbChatMember, ApplicationRequest, DescriptionMessage, \
    DescriptionMessageType, Chat
from database.queries import settings, texts, chat_members, chats, private_chat_messages
from emojis import Emoji
from replacements import replace_placeholders

logger = logging.getLogger(__name__)


CONVERSATION_TIMEOUT = Timeout.HOURS_6


class ApplicationDataKey:
    OTHER_MEMBERS = "other_members"
    SOCIAL = "social"
    DESCRIPTION = "description"
    COMPLETED = "completed"


class State:
    WAITING_START_INLINE_BUTTON = 5
    WAITING_OTHER_MEMBERS = 10
    WAITING_SOCIAL = 20
    WAITING_DESCRIBE_SELF = 30


class ButtonText:
    CANCEL = f"{Emoji.CANCEL} annulla richiesta"
    DONE = f"{Emoji.DONE} invia richiesta"
    SKIP = f"{Emoji.FORWARD} salta"


class Re:
    CANCEL = rf"^(?:{ButtonText.CANCEL})$"
    SKIP = rf"^(?:{ButtonText.SKIP})$"
    BUTTONS = fr"^(?:{ButtonText.CANCEL}|{ButtonText.SKIP})$"


class Command:
    SEND = r"^/invia$"


DESCRIBE_SELF_ALLOWED_MESSAGES_FILTER = (filters.TEXT & ~filters.Regex(Re.BUTTONS)) | filters.VOICE | filters.VIDEO_NOTE | filters.PHOTO | filters.VIDEO | filters.AUDIO

START_REQUEST_REPLY_MARKUP = InlineKeyboardMarkup(
    [[InlineKeyboardButton(f"{Emoji.SPIRAL} iniziamo!", callback_data="startrequest")]]
)


def get_cancel_keyboard(input_field_placeholder: Optional[str] = None):
    keyboard = [
        [KeyboardButton(f"{ButtonText.SKIP}")],
        [KeyboardButton(f"{ButtonText.CANCEL}")]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        input_field_placeholder=input_field_placeholder,
        is_persistent=True
    )


def get_evaluation_keyboard(user_id: int, application_id: int, include_reset=True):
    keyboard = [[
        InlineKeyboardButton(f"{Emoji.GREEN} accetta", callback_data=f"accept:{user_id}:{application_id}"),
        InlineKeyboardButton(f"{Emoji.RED} rifiuta", callback_data=f"reject:{user_id}:{application_id}")
    ]]
    if include_reset:
        reset_button = InlineKeyboardButton(f"{Emoji.RECYCLE} resetta", callback_data=f"reset:{user_id}:{application_id}")
        keyboard[0].insert(1, reset_button)

    return InlineKeyboardMarkup(keyboard)


def get_done_keyboard(input_field_placeholder: Optional[str] = None):
    keyboard = [
        [KeyboardButton(f"{ButtonText.DONE}")],
        [KeyboardButton(f"{ButtonText.CANCEL}")]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        input_field_placeholder=input_field_placeholder,
        is_persistent=True
    )


def get_text(session: Session, ltext_key: str, user: TelegramUser, raise_if_no_fallback: Optional[bool] = True) -> Optional[str]:
    fallback_language = settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    ltext = texts.get_localized_text_with_fallback(
        session,
        ltext_key,
        Language.IT,
        fallback_language=fallback_language,
        raise_if_no_fallback=raise_if_no_fallback
    )
    if ltext:
        text = replace_placeholders(ltext.value, user, session)
        return text


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_ban()
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/start {utilities.log(update)}")

    user.set_started()

    if user.banned:
        logger.info(f"ignoring user message: the user was banned (shadowban: {user.shadowban})")
        if not user.shadowban:
            reason = user.banned_reason or "non fornita"
            sent_message = await update.message.reply_text(f"{Emoji.BANNED} Sei stato bannato dall'utilizzare questo bot. "
                                                           f"Motivo: {utilities.escape_html(reason)}")
            private_chat_messages.save(session, sent_message)
        return ConversationHandler.END

    chat_member = chat_members.get_chat_member(session, update.effective_user.id, Chat.is_users_chat)
    if not chat_member:
        users_chat = chats.get_chat(session, Chat.is_users_chat)
        logger.info(f"no ChatMember record for user {update.effective_user.id} in chat {users_chat.chat_id}, fetching ChatMember...")
        tg_chat_member = await context.bot.get_chat_member(users_chat.chat_id, update.effective_user.id)
        chat_member = DbChatMember.from_chat_member(users_chat.chat_id, tg_chat_member)
        session.add(chat_member)
        session.commit()

    if chat_member.is_member() or (user.last_request and user.last_request.accepted()):
        logger.info("user is already a member of the users chat *or* they were accepted but did not join the chat: sending welcome text for members")
        welcome_text_member = get_text(session, LocalizedTextKey.WELCOME_MEMBER, update.effective_user)
        sent_message = await update.message.reply_text(welcome_text_member)
        private_chat_messages.save(session, sent_message)

        return ConversationHandler.END

    if user.pending_request_id and user.pending_request.sent_to_staff():
        logger.info("user already has a pending request that was sent to the staff")
        sent_message = await update.message.reply_text("Una tua richiesta è già in fase di valutazione. "
                                                       "Attendi che lo staff la esamini")
        private_chat_messages.save(session, sent_message)

        return ConversationHandler.END

    if user.pending_request_id and not user.pending_request.sent_to_staff():
        # we should never enter this, since this ConversationHandler is persistent and if the user uses /start again,
        # the conversation will *not* reset because ConversationHandler.allow_reentry is False

        logger.info("user already has a pending request that was *not* sent to the staff yet, we will reset the request")
        user.reset_evaluation()
        sent_message = await update.message.reply_text("Oops, qualcosa è andato storto :(\nUsa /start per reinviare la richiesta")
        private_chat_messages.save(session, sent_message)

        return ConversationHandler.END  # <-- idea/todo: return correct status based on what we already received

    if user.last_request and user.last_request.rejected():
        logger.info("ignoring: user already went through the application process, but was rejected")
        text = get_text(session, LocalizedTextKey.APPLICATION_REJECTED_ANSWER, update.effective_user, raise_if_no_fallback=False)
        if text:
            sent_message = await update.message.reply_text(text)
            private_chat_messages.save(session, sent_message)

        return ConversationHandler.END

    logger.info("user is not a member of the users chat and doesn't have any pending/completed request")

    welcome_text_not_member = get_text(session, LocalizedTextKey.WELCOME_NOT_MEMBER, update.effective_user)
    sent_message = await update.message.reply_text(welcome_text_not_member, reply_markup=START_REQUEST_REPLY_MARKUP)
    private_chat_messages.save(session, sent_message)

    # exit from the conversation when /start is used: the user will re-enter it for good when they use the inline button
    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_start_application_request_cb(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"start application request cb {utilities.log(update)}")

    request = ApplicationRequest(update.effective_user.id)
    session.add(request)
    session.commit()

    user.pending_request_id = request.id
    session.commit()

    send_other_members_text = get_text(session, LocalizedTextKey.SEND_OTHER_MEMBERS, update.effective_user)
    sent_message = await update.effective_message.reply_html(
        send_other_members_text,
        reply_markup=get_cancel_keyboard("Amici in flytek"),
        quote=False
    )
    private_chat_messages.save(session, sent_message)

    # remove the button
    await update.effective_message.edit_reply_markup(reply_markup=None)

    return State.WAITING_OTHER_MEMBERS


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"application conversation: /cancel command {utilities.log(update)}")

    context.user_data.pop(TempDataKey.APPLICATION_DATA, None)

    # remove any pending request
    user.pending_request_id = None

    cancel_text = get_text(session, LocalizedTextKey.APPLICATION_CANCELED, update.effective_user)
    sent_message = await update.effective_message.reply_text(cancel_text, reply_markup=ReplyKeyboardRemove())
    private_chat_messages.save(session, sent_message)

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_pending_request()
async def on_waiting_other_members_unexpected_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"(unexpected) received non-text message while waiting for other members {utilities.log(update)}")

    send_other_members_text = get_text(session, LocalizedTextKey.SEND_OTHER_MEMBERS, update.effective_user)
    sent_message = await update.message.reply_text(send_other_members_text, reply_markup=get_cancel_keyboard("Membri che conosci"))
    private_chat_messages.save(session, sent_message)

    return State.WAITING_OTHER_MEMBERS


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_pending_request()
async def on_waiting_social_unexpected_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"(unexpected) received non-text message while waiting for social {utilities.log(update)}")

    send_social_text = get_text(session, LocalizedTextKey.SEND_SOCIAL, update.effective_user)
    sent_message = await update.message.reply_text(send_social_text, reply_markup=get_cancel_keyboard("Link ai social"))
    private_chat_messages.save(session, sent_message)

    return State.WAITING_SOCIAL


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_pending_request()
async def on_waiting_description_unexpected_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"(unexpected) received message while waiting for social {utilities.log(update)}")

    send_social_text = get_text(session, LocalizedTextKey.DESCRIBE_SELF, update.effective_user)
    sent_message = await update.message.reply_text(send_social_text, reply_markup=get_cancel_keyboard("Presentati"))
    private_chat_messages.save(session, sent_message)

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_pending_request()
async def on_waiting_other_members_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received other members {utilities.log(update)}")

    user.pending_request.save_other_members(update.message)

    # we don't actually need this but we save it anyway
    description_message = DescriptionMessage(user.pending_request.id, update.effective_message, DescriptionMessageType.OTHER_MEMBERS)
    session.add(description_message)

    send_social_text = get_text(session, LocalizedTextKey.SEND_SOCIAL, update.effective_user)
    sent_message = await update.message.reply_text(send_social_text, reply_markup=get_cancel_keyboard("Link ai tuoi social"))
    private_chat_messages.save(session, sent_message)

    return State.WAITING_SOCIAL


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_pending_request()
async def on_waiting_other_members_skip(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"waiting other members: skip {utilities.log(update)}")

    send_social_text = get_text(session, LocalizedTextKey.SEND_SOCIAL, update.effective_user)
    sent_message = await update.message.reply_text(send_social_text, reply_markup=get_cancel_keyboard("Link ai tuoi social"))
    private_chat_messages.save(session, sent_message)

    return State.WAITING_SOCIAL


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_pending_request()
async def on_waiting_socials_skip(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"waiting socials: skip {utilities.log(update)}")

    describe_self_text = get_text(session, LocalizedTextKey.DESCRIBE_SELF, update.effective_user)
    sent_message = await update.message.reply_text(describe_self_text, reply_markup=get_done_keyboard("Presentati"))
    private_chat_messages.save(session, sent_message)

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_pending_request()
async def on_waiting_social_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received social {utilities.log(update)}")

    user.pending_request.save_social(update.message)

    # we don't actually need this because they are also saved to some dedicated ApplicationRequest fields,
    # but we save it anyway
    description_message = DescriptionMessage(user.pending_request.id, update.effective_message, DescriptionMessageType.SOCIAL)
    session.add(description_message)

    send_description_text = get_text(session, LocalizedTextKey.DESCRIBE_SELF, update.effective_user)
    sent_message = await update.message.reply_text(send_description_text, reply_markup=get_done_keyboard("Presentati"))
    private_chat_messages.save(session, sent_message)

    return State.WAITING_DESCRIBE_SELF


def retry_on_db_locked(callback, *args, **kwargs):
    attempts = 0
    max_attempts = 15
    while True:
        attempts += 1
        try:
            return callback(*args, **kwargs)
        except sqlite3.OperationalError as e:
            logger.warning(f"<{e}> error while running function <{callback.__name__}()>")
            if attempts >= max_attempts:
                logger.info(f"too many attempts: {attempts}")
                raise e


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_pending_request()
async def on_describe_self_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received describe self message {utilities.log(update)}")

    description_message = DescriptionMessage(user.pending_request.id, update.effective_message)
    session.add(description_message)

    if description_message.text:
        # mark as ready only when we receive at least a text
        # if we decide to mark it as ready even if only a single voice message/media is received, make sure the
        # fucntion that sends all the "describe self" messages in the log channel is updated too
        user.pending_request.ready = True

    # we commit now so request.description_messages will be updated with also the message we just received (not tested)
    session.commit()

    logger.info(f"saved description message, total messages: {len(user.pending_request.description_messages)}")

    text = get_text(session, LocalizedTextKey.DESCRIBE_SELF_SEND_MORE, update.effective_user)
    reply_markup = get_done_keyboard("Invia altri messaggi/media")

    if not update.message.media_group_id:
        # sending this message is needed if we want the "done" keyboard to appear after the user sends the message
        sent_message = await update.message.reply_text(text, reply_markup=reply_markup, quote=True)
        private_chat_messages.save(session, sent_message)

        # pop this temp key if the message doesn't belong to an album
        context.user_data.pop(TempDataKey.ALBUM_ANSWERED, None)
    else:
        # send a reply only to the first album message received
        if TempDataKey.ALBUM_ANSWERED not in context.user_data:
            context.user_data[TempDataKey.ALBUM_ANSWERED] = []

        if update.message.media_group_id not in context.user_data[TempDataKey.ALBUM_ANSWERED]:
            logger.info(f"first time we receive a message belonging to album {update.message.media_group_id}, answering...")
            sent_message = await update.message.reply_text(text, reply_markup=reply_markup, quote=True)
            private_chat_messages.save(session, sent_message)
            context.user_data[TempDataKey.ALBUM_ANSWERED].append(update.message.media_group_id)
        else:
            # do not answer multiple times to the same album
            logger.info(f"not answering to message from album {update.message.media_group_id} because we already did")

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_done_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"done button {utilities.log(update)}")

    context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.DESCRIPTION].append(update.message)
    logger.info(f"saved messages: {len(context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.DESCRIPTION])}")

    # mark as completed as soon as we receive one message
    context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.COMPLETED] = True

    return State.WAITING_DESCRIBE_SELF


async def send_application_log_message(bot: Bot, log_chat_id: int, request: ApplicationRequest, user: TelegramUser):
    # create and send the log message with user info, social, and other members
    user_mention = utilities.mention_escaped(user)
    user_username = f"@{user.username}" if user.username else "username non impostato"
    base_text = f"{Emoji.SPARKLE} <b>nuova #richiesta</b> • {request.id_hashtag()} • #pendente • #nojoin\n\n" \
                f"{Emoji.PERSON} <b>utente</b>\n" \
                f"• {user_mention}\n" \
                f"• {user_username}\n" \
                f"• #id{user.id}"

    other_members_text = utilities.escape_html(request.other_members_text or "non forniti")
    base_text += f"\n\n{Emoji.PEOPLE} <b>utenti garanti</b>\n{other_members_text}"

    social_text = utilities.escape_html(request.social_text or "non forniti")
    base_text += f"\n\n{Emoji.PHONE} <b>social</b>\n{social_text}"

    # no idea why but we *need* large timeouts
    timeouts = dict(connect_timeout=300, read_timeout=300, write_timeout=300)

    logger.debug("sending log message...")
    log_message: Message = await bot.send_message(
        chat_id=log_chat_id,
        text=base_text,
        **timeouts
    )
    request.set_log_message(log_message)

    # we have to send the keyboard in a new log message because if we send it with the log channel post, Telegram apps
    # won't display the comments bar
    reply_markup = get_evaluation_keyboard(request.user_id, request.id)
    evaluation_buttons_message: Message = await log_message.reply_html(
        f"Decidi che fare con la richiesta di {request.user.mention(escape=True)}:",
        reply_markup=reply_markup,
        do_quote=True
    )
    request.set_evaluation_buttons_message(evaluation_buttons_message)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_pending_request()
async def on_timeout_or_done(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"conversation timed out or user is done {utilities.log(update)}")

    # make sure to pop this key from user_data
    context.user_data.pop(TempDataKey.ALBUM_ANSWERED, None)

    # on timeout, the last received update is passed to the handler
    # so if the last update is not the "done" button, then it means the conversation timeout-out
    done_button_pressed = update.message.text and re.search(rf"^{ButtonText.DONE}$", update.message.text, re.I)

    if not user.pending_request.ready and done_button_pressed:
        logger.info("user didn't complete the conversation: warning user, but waiting for more")
        text = get_text(session, LocalizedTextKey.APPLICATION_NOT_READY, update.effective_user)
        sent_message = await update.message.reply_text(text, reply_markup=get_done_keyboard())
        private_chat_messages.save(session, sent_message)

        return State.WAITING_DESCRIBE_SELF
    elif not user.pending_request.ready and not done_button_pressed:
        # await update.message.reply_text("Per favore invia almeno un messaggio")
        # return
        logger.info(f"user didn't complete the conversation (timeout: {CONVERSATION_TIMEOUT} seconds): canceling operation")
        text = get_text(session, LocalizedTextKey.APPLICATION_TIMEOUT, update.effective_user)
        sent_message = await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        private_chat_messages.save(session, sent_message)

        logger.info("forgetting current pending request")
        user.pending_request_id = None

        return ConversationHandler.END

    logger.info("all requested data has been submitted: sending to staff")

    text = get_text(session, LocalizedTextKey.APPLICATION_SENT_TO_STAFF, update.effective_user)
    sent_message = await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
    private_chat_messages.save(session, sent_message)

    # save the message_id of the message we sent to the user saying that their request has been sent to the admins
    user.pending_request.request_sent_message_message_id = sent_message.message_id

    log_chat = chats.get_chat(session, Chat.is_log_chat)
    evaluation_chat = chats.get_chat(session, Chat.is_evaluation_chat)

    await send_application_log_message(
        bot=context.bot,
        log_chat_id=log_chat.chat_id,
        request=user.pending_request,
        user=update.effective_user
    )

    return ConversationHandler.END


approval_mode_conversation_handler = ConversationHandler(
    name="approval_conversation",
    persistent=True,
    allow_reentry=False,  # if inside the conversation, it will not be restarted if an entry point is triggered
    entry_points=[
        CommandHandler(["start"], on_start_command, filters=filters.ChatType.PRIVATE),
        CallbackQueryHandler(on_start_application_request_cb, pattern=r"startrequest")
    ],
    states={
        State.WAITING_OTHER_MEMBERS: [
            MessageHandler(~filters.TEXT, on_waiting_other_members_unexpected_message_received),
            MessageHandler(filters.TEXT & filters.Regex(Re.SKIP), on_waiting_other_members_skip),
            MessageHandler(filters.TEXT & ~filters.Regex(Re.CANCEL), on_waiting_other_members_received),
        ],
        State.WAITING_SOCIAL: [
            MessageHandler(~filters.TEXT & ~filters.CAPTION, on_waiting_social_unexpected_message_received),
            MessageHandler(filters.TEXT & filters.Regex(Re.SKIP), on_waiting_socials_skip),
            MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.Regex(Re.CANCEL), on_waiting_social_received),
        ],
        State.WAITING_DESCRIBE_SELF: [
            # make this handler blocking: forwarding many messages to a chat may require some time
            MessageHandler(filters.TEXT & filters.Regex(rf"^{ButtonText.DONE}$"), on_timeout_or_done, block=True),
            MessageHandler(DESCRIBE_SELF_ALLOWED_MESSAGES_FILTER, on_describe_self_received),
            MessageHandler(~filters.TEXT, on_waiting_description_unexpected_message_received),
        ],
        ConversationHandler.TIMEOUT: [
            # on timeout, the *last update* is broadcasted to all handlers. it might be a callback query or a text
            # make this handler blocking: forwarding many messages to a chat may require some time
            MessageHandler(filters.ALL, on_timeout_or_done, block=True),
        ]
    },
    fallbacks=[
        MessageHandler(filters.TEXT & filters.Regex(Re.CANCEL), on_cancel),
    ],
    conversation_timeout=CONVERSATION_TIMEOUT
)

HANDLERS = (
    # (CommandHandler(["start"], on_start_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (approval_mode_conversation_handler, Group.NORMAL),
)
