import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Bot, Message, InputMediaPhoto
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser
from telegram.constants import MessageLimit
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, PrefixHandler, MessageHandler
from telegram.ext import CommandHandler
from telegram.ext import filters

from database.models import User, ChatMember as DbChatMember
from database.queries import settings, texts, chat_members, chats, private_chat_messages
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

    fallback_language = settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()

    if chat_member.is_member() and False:
        logger.info("user is already a member of the users chat")
        welcome_text_member = texts.get_localized_text_with_fallback(
            session,
            LocalizedTextKey.WELCOME_MEMBER,
            Language.IT,
            fallback_language=fallback_language
        )
        text = replace_placeholders(welcome_text_member.value, update.effective_user, session)
        sent_message = await update.message.reply_text(text)
        private_chat_messages.save(session, sent_message)
        user.set_started()
        return ConversationHandler.END

    logger.info("user is not a member of the users chat")

    context.user_data[TempDataKey.APPLICATION_DATA] = {
        ApplicationDataKey.OTHER_MEMBERS: None,
        ApplicationDataKey.SOCIAL: None,
        ApplicationDataKey.DESCRIPTION: [],
        ApplicationDataKey.COMPLETED: False
    }

    welcome_text_not_member = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.WELCOME_NOT_MEMBER,
        Language.IT,
        fallback_language=fallback_language
    )

    text = replace_placeholders(welcome_text_not_member.value, update.effective_user, session)
    sent_message = await update.message.reply_text(text)
    private_chat_messages.save(session, sent_message)

    send_other_members_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.SEND_OTHER_MEMBERS,
        Language.IT,
        fallback_language=fallback_language
    )
    text = replace_placeholders(send_other_members_text.value, update.effective_user, session)
    sent_message = await update.message.reply_text(text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    user.set_started()

    return State.WAITING_OTHER_MEMBERS


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"application conversation: /cancel command {utilities.log(update)}")

    context.user_data.pop(TempDataKey.APPLICATION_DATA, None)

    cancel_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.APPLICATION_CANCELED,
        Language.IT,
        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    )
    text = replace_placeholders(cancel_text.value, update.effective_user, session)
    sent_message = await update.effective_message.reply_text(text, reply_markup=ReplyKeyboardRemove())
    private_chat_messages.save(session, sent_message)

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_other_members_unexpected_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"(unexpected) received non-text message while waiting for other members {utilities.log(update)}")

    send_other_members_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.SEND_OTHER_MEMBERS,
        Language.IT,
        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    )
    text = replace_placeholders(send_other_members_text.value, update.effective_user, session)
    sent_message = await update.message.reply_text(text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_OTHER_MEMBERS


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_social_unexpected_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"(unexpected) received non-text message while waiting for social {utilities.log(update)}")

    send_social_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.SEND_SOCIAL,
        Language.IT,
        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    )
    text = replace_placeholders(send_social_text.value, update.effective_user, session)
    sent_message = await update.message.reply_text(text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_SOCIAL


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_description_unexpected_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"(unexpected) received message while waiting for social {utilities.log(update)}")

    send_social_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.DESCRIBE_SELF,
        Language.IT,
        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    )
    text = replace_placeholders(send_social_text.value, update.effective_user, session)
    sent_message = await update.message.reply_text(text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_other_members_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received other members {utilities.log(update)}")

    context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.OTHER_MEMBERS] = update.message.text_html

    send_social_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.SEND_SOCIAL,
        Language.IT,
        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    )
    text = replace_placeholders(send_social_text.value, update.effective_user, session)
    sent_message = await update.message.reply_text(text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_SOCIAL


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_other_members_skip(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"waiting other members: skip {utilities.log(update)}")

    send_social_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.SEND_SOCIAL,
        Language.IT,
        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    )
    text = replace_placeholders(send_social_text.value, update.effective_user, session)
    sent_message = await update.message.reply_text(text, reply_markup=get_cancel_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_SOCIAL


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_socials_skip(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"waiting socials: skip {utilities.log(update)}")

    describe_self_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.DESCRIBE_SELF,
        Language.IT,
        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    )
    text = replace_placeholders(describe_self_text.value, update.effective_user, session)
    sent_message = await update.message.reply_text(text, reply_markup=get_done_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_waiting_social_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received social {utilities.log(update)}")

    context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.SOCIAL] = update.message.text_html

    send_description_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.DESCRIBE_SELF,
        Language.IT,
        fallback_language=settings.get_or_create(session, BotSettingKey.FALLBACK_LANGAUGE).value()
    )
    text = replace_placeholders(send_description_text.value, update.effective_user, session)
    sent_message = await update.message.reply_text(text, reply_markup=get_done_keyboard())
    private_chat_messages.save(session, sent_message)

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_describe_self_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received describe self message {utilities.log(update)}")

    context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.DESCRIPTION].append(update.message)
    logger.info(f"saved messages: {len(context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.DESCRIPTION])}")

    # mark as completed as soon as we receive one message
    context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.COMPLETED] = True

    # this is *not needed* if ReplyKeyboardMarkup.is_persistent is True (see #29)
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


async def send_application_to_staff(bot: Bot, chat_id: int, application_data, user: TelegramUser):
    # there must be at least one message
    description_messages: List[Message] = application_data.pop(ApplicationDataKey.DESCRIPTION)

    text_messages: List[Message] = []
    photo_or_video_messages: List[Message] = []
    voice_or_video_note_messages: List[Message] = []

    # we will link them later
    sent_attachment_messages: List[Message] = []

    for message in description_messages:
        if message.photo or message.video:
            photo_or_video_messages.append(message)
        elif message.voice or message.video_note:
            voice_or_video_note_messages.append(message)
        elif message.text:
            text_messages.append(message)
        else:
            logger.warning(f"unexpected description message: {message}")

    # first: send text messages
    if text_messages:
        text = f"{Emoji.LINE} <b>descrizione</b>"

        for message in text_messages:
            if len(text) + len(message.text_html) > MessageLimit.MAX_TEXT_LENGTH:
                sent_message = await bot.send_message(chat_id, text)
                sent_attachment_messages.append(sent_message)
                text = ""
            else:
                text += f"\n{message.text_html}"

        if text:
            # send what's left
            sent_message = await bot.send_message(chat_id, text)
            sent_attachment_messages.append(sent_message)

    # then: send photos/videos as albums
    input_medias = []
    for i, message in enumerate(photo_or_video_messages):
        if message.photo:
            input_media = InputMediaPhoto(message.photo[-1].file_id, caption=message.caption)
        elif message.video:
            input_media = InputMediaPhoto(message.video.file_id, caption=message.caption)
        else:
            logger.warning(f"unexpected video/photo message: {message}")
            continue

        input_medias.append(input_media)

        if len(input_medias) == 10:
            logger.debug("album limit reached: sending media group...")
            sent_messages = await bot.send_media_group(chat_id, media=input_medias)
            # save only the first one to link
            sent_attachment_messages.append(sent_messages[0])
            input_medias = []

    if input_medias:
        # send what's left
        sent_messages = await bot.send_media_group(chat_id, media=input_medias)
        # save only the first one to link
        sent_attachment_messages.append(sent_messages[0])

    # then: send voice or video messages
    for message in voice_or_video_note_messages:
        if message.voice:
            sent_message = await bot.send_voice(chat_id, message.voice.file_id)
        elif message.video_note:
            sent_message = await bot.send_video_note(chat_id, message.video_note.file_id)
        else:
            logger.warning(f"unexpected voice/video note message: {message}")
            continue

        sent_attachment_messages.append(sent_message)

    user_mention = user.mention_html(name=utilities.escape_html(user.full_name))
    user_username = f"@{user.username}" if user.username else "non impostato"
    staff_chat_application_message = f"#RICHIESTA\n\n{Emoji.USER_ICON} {user_mention}\n{Emoji.SPIRAL} {user_username}\n{Emoji.HASHTAG} #user{user.id}"

    other_members_text = utilities.escape_html(application_data[ApplicationDataKey.OTHER_MEMBERS] or "non forniti")
    staff_chat_application_message += f"\n\n{Emoji.LINE} <b>utenti garanti</b>\n{other_members_text}"

    social_text = utilities.escape_html(application_data[ApplicationDataKey.SOCIAL] or "non forniti")
    staff_chat_application_message += f"\n\n{Emoji.LINE} <b>social</b>\n{social_text}"

    # staff_chat_application_message += f"\n\n{Emoji.LINE} <b>descrizione</b>\nda messaggio in risposta in poi"

    await sent_attachment_messages[0].reply_html(staff_chat_application_message, quote=True)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_timeout_or_done(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"conversation timed out or user is done")

    application_data = context.user_data.pop(TempDataKey.APPLICATION_DATA, None)
    if not application_data:
        raise ValueError("no application data")

    if not application_data[ApplicationDataKey.COMPLETED]:
        logger.info("user didn't complete the conversation: cancel")
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
        chat_id=staff_chat.chat_id,
        application_data=application_data,
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
            MessageHandler(filters.TEXT & filters.Regex(rf"^{ButtonText.DONE}$"), on_timeout_or_done),
            MessageHandler(DESCRIBE_SELF_ALLOWED_MESSAGES_FILTER, on_describe_self_received),
            MessageHandler(~filters.TEXT, on_waiting_description_unexpected_message_received),
        ],
        ConversationHandler.TIMEOUT: [
            # on timeout, the *last update* is broadcasted to all handlers. it might be a callback query or a text
            MessageHandler(filters.ALL, on_timeout_or_done),
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
