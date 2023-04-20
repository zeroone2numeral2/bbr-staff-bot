import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, PrefixHandler, MessageHandler
from telegram.ext import CommandHandler
from telegram.ext import filters

from database.models import User, ChatMember as DbChatMember
from database.queries import settings, texts, chat_members, chats
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


DESCRIBE_SELF_ALLOWED_MESSAGES_FILTER = (filters.TEXT & ~filters.Regex(Re.BUTTONS)) | filters.VOICE | filters.VIDEO_NOTE | filters.PHOTO | filters.VIDEO | filters.AUDIO


def get_cancel_keyboard():
    keyboard = [
        [KeyboardButton(f"{ButtonText.SKIP}")],
        [KeyboardButton(f"{ButtonText.CANCEL}")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_done_keyboard():
    keyboard = [
        [KeyboardButton(f"{ButtonText.DONE}")],
        [KeyboardButton(f"{ButtonText.CANCEL}")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/start {utilities.log(update)}")

    chat_member = chat_members.get_users_chat_chat_member(session, update.effective_user.id)
    if not chat_member:
        users_chat = chats.get_users_chat(session)
        logger.info(f"no record for user {update.effective_user.id} in chat {users_chat.chat_id}, fetching ChatMember...")
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
        await update.message.reply_text(text)
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
    await update.message.reply_text(text)

    send_other_members_text = texts.get_localized_text_with_fallback(
        session,
        LocalizedTextKey.SEND_OTHER_MEMBERS,
        Language.IT,
        fallback_language=fallback_language
    )
    text = replace_placeholders(send_other_members_text.value, update.effective_user, session)
    await update.message.reply_text(text, reply_markup=get_cancel_keyboard())

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
    await update.effective_message.reply_text(text, reply_markup=ReplyKeyboardRemove())

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
    await update.message.reply_text(text, reply_markup=get_cancel_keyboard())

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
    await update.message.reply_text(text, reply_markup=get_cancel_keyboard())

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
    await update.message.reply_text(text, reply_markup=get_cancel_keyboard())

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
    await update.message.reply_text(text, reply_markup=get_cancel_keyboard())

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
    await update.message.reply_text(text, reply_markup=get_cancel_keyboard())

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
    await update.message.reply_text(text, reply_markup=get_done_keyboard())

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
    await update.message.reply_text(text, reply_markup=get_done_keyboard())

    return State.WAITING_DESCRIBE_SELF


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_describe_self_received(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"received describe self message {utilities.log(update)}")

    context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.DESCRIPTION].append(update.message)
    logger.info(f"saved messages: {len(context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.DESCRIPTION])}")

    # mark as completed as soon as we receive one message
    context.user_data[TempDataKey.APPLICATION_DATA][ApplicationDataKey.COMPLETED] = True

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


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"conversation timed out")

    application_data = context.user_data.pop(TempDataKey.APPLICATION_DATA, None)
    if not application_data:
        raise ValueError("no application data")

    if application_data[ApplicationDataKey.COMPLETED]:
        # send to staff
        await update.message.reply_text("timeout: sent staff", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("timeout: canceled", reply_markup=ReplyKeyboardRemove())

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
            MessageHandler(filters.TEXT & filters.Regex(rf"^{ButtonText.DONE}$"), on_timeout),
            MessageHandler(DESCRIBE_SELF_ALLOWED_MESSAGES_FILTER, on_describe_self_received),
            MessageHandler(~filters.TEXT, on_waiting_description_unexpected_message_received),
        ],
        ConversationHandler.TIMEOUT: [
            # on timeout, the *last update* is broadcasted to all users. it might be a callback query or a text
            MessageHandler(filters.ALL, on_timeout),
        ]
    },
    fallbacks=[
        MessageHandler(filters.TEXT & filters.Regex(Re.CANCEL), on_cancel),
    ],
    conversation_timeout=Timeout.SECONDS_30
)

HANDLERS = (
    # (CommandHandler('start', on_start_command, filters.ChatType.PRIVATE), Group.NORMAL),
    (approval_mode_conversation_handler, Group.NORMAL),
)
