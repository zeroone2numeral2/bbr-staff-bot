import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Bot, Message, InputMediaPhoto
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser
from telegram.constants import MessageLimit
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, PrefixHandler, MessageHandler
from telegram.ext import CommandHandler
from telegram.ext import filters

from database.models import User, ChatMember as DbChatMember, ApplicationRequest, DescriptionMessage, \
    DescriptionMessageType
from database.queries import settings, texts, chat_members, chats, private_chat_messages, application_requests
import decorators
import utilities
from emojis import Emoji
from replacements import replace_placeholders
from constants import LANGUAGES, BotSettingKey, LocalizedTextKey, Group, Language, TempDataKey, COMMAND_PREFIXES, \
    Timeout

logger = logging.getLogger(__name__)


class ApplicationDataKey:
    OTHER_MEMBERS = "other_members"
    SOCIAL = "social"
    DESCRIPTION = "description"
    COMPLETED = "completed"


class State:
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


def get_text(session: Session, ltext_key: str, user: TelegramUser) -> str:
    fallback_language = settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    ltext = texts.get_localized_text_with_fallback(
        session,
        ltext_key,
        Language.IT,
        fallback_language=fallback_language
    )
    text = replace_placeholders(ltext.value, user, session)
    return text


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/start {utilities.log(update)}")

    chat_member = chat_members.get_users_chat_chat_member(session, update.effective_user.id)
    if not chat_member:
        users_chat = chats.get_users_chat(session)
        logger.info(f"no ChatMember record for user {update.effective_user.id} in chat {users_chat.chat_id}, fetching ChatMember...")
        tg_chat_member = await context.bot.get_chat_member(users_chat.chat_id, update.effective_user.id)
        chat_member = DbChatMember.from_chat_member(users_chat.chat_id, tg_chat_member)
        session.add(chat_member)
        session.commit()

    if chat_member.is_member() and False:
        logger.info("user is already a member of the users chat")
        welcome_text_member = get_text(session, LocalizedTextKey.WELCOME_MEMBER, update.effective_user)
        sent_message = await update.message.reply_text(welcome_text_member)
        private_chat_messages.save(session, sent_message)
        user.set_started()
        return ConversationHandler.END

    logger.info("user is not a member of the users chat")

    request = ApplicationRequest(update.effective_user.id)
    session.add(request)
    session.commit()
    context.user_data[TempDataKey.APPLICATION_ID] = request.id

    welcome_text_not_member = get_text(session, LocalizedTextKey.WELCOME_NOT_MEMBER, update.effective_user)
    sent_message = await update.message.reply_text(welcome_text_not_member)
    private_chat_messages.save(session, sent_message)

    send_other_members_text = get_text(session, LocalizedTextKey.SEND_OTHER_MEMBERS, update.effective_user)
    sent_message = await update.message.reply_text(send_other_members_text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    user.set_started()

    return State.WAITING_OTHER_MEMBERS


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"application conversation: /cancel command {utilities.log(update)}")

    context.user_data.pop(TempDataKey.APPLICATION_DATA, None)

    cancel_text = get_text(session, LocalizedTextKey.APPLICATION_CANCELED, update.effective_user)
    sent_message = await update.effective_message.reply_text(cancel_text, reply_markup=ReplyKeyboardRemove())
    private_chat_messages.save(session, sent_message)

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_other_members_unexpected_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"(unexpected) received non-text message while waiting for other members {utilities.log(update)}")

    send_other_members_text = get_text(session, LocalizedTextKey.SEND_OTHER_MEMBERS, update.effective_user)
    sent_message = await update.message.reply_text(send_other_members_text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_OTHER_MEMBERS


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_social_unexpected_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"(unexpected) received non-text message while waiting for social {utilities.log(update)}")

    send_social_text = get_text(session, LocalizedTextKey.DESCRIBE_SELF, update.effective_user)
    sent_message = await update.message.reply_text(send_social_text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_SOCIAL


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_description_unexpected_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"(unexpected) received message while waiting for social {utilities.log(update)}")

    send_social_text = get_text(session, LocalizedTextKey.DESCRIBE_SELF, update.effective_user)
    sent_message = await update.message.reply_text(send_social_text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_other_members_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received other members {utilities.log(update)}")

    # context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.OTHER_MEMBERS] = update.message.text_html

    request_id = context.user_data[TempDataKey.APPLICATION_ID]
    request: ApplicationRequest = application_requests.get_by_id(session, request_id)
    request.save_other_members(update.message)

    # we don't actually need this but we save it anyway
    description_message = DescriptionMessage(request.id, update.effective_message, DescriptionMessageType.OTHER_MEMBERS)
    session.add(description_message)
    request.updated()

    send_social_text = get_text(session, LocalizedTextKey.SEND_SOCIAL, update.effective_user)
    sent_message = await update.message.reply_text(send_social_text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_SOCIAL


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_other_members_skip(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"waiting other members: skip {utilities.log(update)}")

    send_social_text = get_text(session, LocalizedTextKey.SEND_SOCIAL, update.effective_user)
    sent_message = await update.message.reply_text(send_social_text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_SOCIAL


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_socials_skip(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"waiting socials: skip {utilities.log(update)}")

    describe_self_text = get_text(session, LocalizedTextKey.DESCRIBE_SELF, update.effective_user)
    sent_message = await update.message.reply_text(describe_self_text, reply_markup=get_done_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_social_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received social {utilities.log(update)}")

    # context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.SOCIAL] = update.message.text_html
    request_id = context.user_data[TempDataKey.APPLICATION_ID]
    request: ApplicationRequest = application_requests.get_by_id(session, request_id)
    request.save_social(update.message)

    # we don't actually need this because they are also saved toApplicationRequest  but we save it anyway
    description_message = DescriptionMessage(request.id, update.effective_message, DescriptionMessageType.SOCIAL)
    session.add(description_message)
    request.updated()

    send_description_text = get_text(session, LocalizedTextKey.DESCRIBE_SELF, update.effective_user)
    sent_message = await update.message.reply_text(send_description_text, reply_markup=get_done_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_describe_self_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received describe self message {utilities.log(update)}")

    # context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.DESCRIPTION].append(update.message)

    request_id = context.user_data[TempDataKey.APPLICATION_ID]
    request: ApplicationRequest = application_requests.get_by_id(session, request_id)
    description_message = DescriptionMessage(request.id, update.effective_message)
    session.add(description_message)
    request.ready = True
    request.updated()

    logger.info(f"saved description message")

    # this is actually needed if we want the "done" keyboard to appear after the user sends the message
    """
    sent_message = await update.message.reply_text(
        "Salvato! Se vuoi puoi inviare altri messaggi, oppure invia la tua richiesta quando sei convint*",
        reply_markup=get_done_keyboard()
    )
    private_chat_messages.save(session, sent_message)
    """

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


async def send_application_to_staff(bot: Bot, staff_chat_id: int, log_chat_id: int, request: ApplicationRequest, user: TelegramUser):
    # we will save the whole list just in case we will need to link them, but we actually need just the first one
    # because it's the message we reply to
    sent_attachment_messages: List[Message] = []

    messages_to_send_as_album: List[DescriptionMessage] = []
    description_message: DescriptionMessage
    for description_message in request.description_messages:
        if description_message.is_social_message() or description_message.is_other_members_message():
            continue

        if description_message.can_be_grouped():
            messages_to_send_as_album.append(description_message)
            continue

        if description_message.text:
            sent_message = await bot.send_message(log_chat_id, description_message.text_html)
        elif description_message.type == DescriptionMessageType.VOICE:
            sent_message = await bot.send_voice(log_chat_id, description_message.media_file_id, caption=description_message.caption_html)
        elif description_message.type == DescriptionMessageType.VIDEO_MESSAGE:
            sent_message = await bot.send_video_note(log_chat_id, description_message.media_file_id)
        else:
            logger.warning(f"unexpected description message: {description_message}")
            continue

        sent_attachment_messages.append(sent_message)
        description_message.set_log_message(sent_message)

    input_medias = []
    for i, description_message in enumerate(messages_to_send_as_album):
        input_medias.append(description_message.get_input_media())

        if len(input_medias) == 10:
            logger.debug("album limit reached: sending media group...")
            sent_messages = await bot.send_media_group(log_chat_id, media=input_medias)
            sent_attachment_messages.append(sent_messages[0])  # we will link just the first one
            # save sent log message
            for j, sent_message in enumerate(sent_messages):
                index = i + j
                logger.debug(f"saving log message with index {index}...")
                messages_to_send_as_album[index].set_log_message(sent_message)

            input_medias = []

    medias_count = len(input_medias)
    if input_medias:
        # send what's left
        sent_messages = await bot.send_media_group(staff_chat_id, media=input_medias)
        sent_attachment_messages.append(sent_messages[0])  # we will link just the first one
        for i, sent_message in enumerate(sent_messages):
            index = (medias_count - i) * -1  # go through the list from the last item
            logger.debug(f"saving log message with index {index}...")
            messages_to_send_as_album[index].set_log_message(sent_message)

    user_mention = user.mention_html(name=utilities.escape_html(user.full_name))
    user_username = f"@{user.username}" if user.username else "non impostato"
    base_text = f"#RICHIESTA\n\n{Emoji.USER_ICON} {user_mention}\n{Emoji.SPIRAL} {user_username}\n{Emoji.HASHTAG} #user{user.id}"

    other_members_text = utilities.escape_html(request.other_members_text or "non forniti")
    base_text += f"\n\n{Emoji.LINE} <b>utenti garanti</b>\n{other_members_text}"

    social_text = utilities.escape_html(request.social_text or "non forniti")
    base_text += f"\n\n{Emoji.LINE} <b>social</b>\n{social_text}"

    logger.debug("sending log message...")
    log_message: Message = await sent_attachment_messages[0].reply_html(base_text, quote=True, connect_timeout=300)
    request.set_log_message(log_message)

    if staff_chat_id != log_chat_id:
        logger.debug("sending staff message...")
        staff_message_text = f"{base_text}\n\n{Emoji.LINE} <b>allegati</b>\n<a href=\"{request.log_message_link()}\">vai al log</a>"
        staff_message: Message = await bot.send_message(staff_chat_id, staff_message_text, connect_timeout=300)
        request.set_staff_message(staff_message)
    else:
        request.set_staff_message(log_message)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_timeout_or_done(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"conversation timed out or user is done")

    request_id = context.user_data.pop(TempDataKey.APPLICATION_ID, None)
    if not request_id:
        raise ValueError("no request id")

    request: ApplicationRequest = application_requests.get_by_id(session, request_id)
    if not request.ready:
        # await update.message.reply_text("Per favore invia almeno un messaggio")
        # return
        logger.info("user didn't complete the conversation: canceling operation")
        text = get_text(session, LocalizedTextKey.APPLICATION_TIMEOUT, update.effective_user)
        sent_message = await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        private_chat_messages.save(session, sent_message)
        return ConversationHandler.END

    logger.info("all requested data has been submitted: sending to staff")

    text = get_text(session, LocalizedTextKey.APPLICATION_SENT_TO_STAFF, update.effective_user)
    sent_message = await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
    private_chat_messages.save(session, sent_message)

    staff_chat = chats.get_staff_chat(session)
    await send_application_to_staff(
        bot=context.bot,
        log_chat_id=-1001922853416,
        staff_chat_id=staff_chat.chat_id,
        request=request,
        user=update.effective_user
    )

    return ConversationHandler.END


approval_mode_conversation_handler = ConversationHandler(
    name="approval_conversation",
    entry_points=[CommandHandler(["start"], on_start_command)],
    states={
        State.WAITING_OTHER_MEMBERS: [
            MessageHandler(~filters.TEXT, on_waiting_other_members_unexpected_message_received),
            MessageHandler(filters.TEXT & filters.Regex(Re.SKIP), on_waiting_other_members_skip),
            MessageHandler(filters.TEXT & ~filters.Regex(Re.CANCEL), on_waiting_other_members_received),
        ],
        State.WAITING_SOCIAL: [
            MessageHandler(~filters.TEXT, on_waiting_social_unexpected_message_received),
            MessageHandler(filters.TEXT & filters.Regex(Re.SKIP), on_waiting_socials_skip),
            MessageHandler(filters.TEXT & ~filters.Regex(Re.CANCEL), on_waiting_social_received),
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
    conversation_timeout=Timeout.MINUTES_20
)

HANDLERS = (
    # (CommandHandler('start', on_start_command, filters.ChatType.PRIVATE), Group.NORMAL),
    (approval_mode_conversation_handler, Group.NORMAL),
)
