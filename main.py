import logging
import re
import time
from typing import Optional, Tuple, List, Union

import pytz
from sqlalchemy.orm import Session
from sqlalchemy import update as sqlalchemy_update, true, ChunkedIteratorResult, select
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberAdministrator, User as TelegramUser, \
    ChatMemberOwner, ChatMember, Message, BotCommand, BotCommandScopeAllPrivateChats, ChatMemberMember, \
    ChatMemberRestricted, ChatMemberLeft, ChatMemberBanned
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Defaults, filters, MessageHandler, \
    CallbackQueryHandler, ChatMemberHandler, PrefixHandler, Application, ExtBot, ConversationHandler, TypeHandler, \
    CallbackContext
from telegram.ext.filters import MessageFilter
from telegram import helpers

from database import engine
from database.base import get_session
from database.models import User, UserMessage, Chat, chat_member_to_dict, ChatAdministrator, AdminMessage, \
    BotSetting, ValueType, LocalizedText
from database.queries import settings, chats, user_messages, admin_messages, texts
import decorators
import utilities
from emojis import Emoji
from constants import LANGUAGES, Language, ADMIN_HELP, COMMAND_PREFIXES, State, CACHE_TIME, TempDataKey, \
    BOT_SETTINGS_DEFAULTS, BotSettingKey, LocalizedTextKey, LOCALIZED_TEXTS_DESCRIPTION, LOCALIZED_TEXTS_TRIGGERS
from config import config

logger = logging.getLogger(__name__)

defaults = Defaults(
    parse_mode=ParseMode.HTML,
    disable_web_page_preview=True,
    tzinfo=pytz.timezone('Europe/Rome'),
    quote=False
)


def get_language_code(selected_language_code, telegram_language_code):
    if selected_language_code:
        return selected_language_code

    return telegram_language_code or Language.EN


def get_start_reply_markup(start_message_language: str, welcome_texts) -> Optional[InlineKeyboardMarkup]:
    keyboard = [[]]

    for welcome_text in welcome_texts:
        if welcome_text.language not in LANGUAGES:
            logger.debug(f"welcome text found for language {welcome_text.language}, but not available in LANGUAGES")
            continue
        if start_message_language != welcome_text.language:
            emoji = LANGUAGES[welcome_text.language]["emoji"]
            button = InlineKeyboardButton(emoji, callback_data=f"setlangstart:{welcome_text.language}")
            keyboard[0].append(button)

    if len(keyboard[0]) < 1:
        return

    return InlineKeyboardMarkup(keyboard)


def get_all_languages_reply_markup(user_language: str) -> InlineKeyboardMarkup:
    keyboard = [[]]

    for language_code, language_data in LANGUAGES.items():
        if user_language != language_code:
            button = InlineKeyboardButton(language_data["emoji"], callback_data=f"setlang:{language_code}")
            keyboard[0].append(button)

    return InlineKeyboardMarkup(keyboard)


PLACEHOLDER_REPLACEMENTS = {
    "{NAME}": lambda u: utilities.escape_html(u.first_name),
    "{SURNAME}": lambda u: utilities.escape_html(u.last_name),
    "{FULLNAME}": lambda u: utilities.escape_html(u.full_name),
    "{USERNAME}": lambda u: f"@{u.username}" if u.username else "-",
    "{MENTION}": lambda u: helpers.mention_html(u.id, utilities.escape_html(u.first_name)),
    "{LANG}": lambda u: LANGUAGES[u.language_code]["desc"] if u.language_code else LANGUAGES[Language.EN]["desc"],
    "{LANGEMOJI}": lambda u: LANGUAGES[u.language_code]["emoji"] if u.language_code else LANGUAGES[Language.EN]["emoji"]
}


def replace_placeholders(text: str, user: TelegramUser):
    for placeholder, repl_func in PLACEHOLDER_REPLACEMENTS.items():
        text = text.replace(placeholder, repl_func(user))

    return text


def get_localized_text_resume_text(session: Session, setting_key: str):
    result = texts.get_texts(session, setting_key)
    ltexts_statuses = {}

    ltext: LocalizedText
    for ltext in result:
        ltexts_statuses[ltext.language] = "set" if ltext.value else "<b>not set</b>"

    for lang_code, lang_data in LANGUAGES.items():
        if lang_code in ltexts_statuses:
            continue

        ltexts_statuses[lang_code] = "<b>not set</b>"

    text = ""
    for lang_code, current_status in ltexts_statuses.items():
        text += f"\n{LANGUAGES[lang_code]['emoji']} -> {current_status}"

    return text.strip()


def get_localized_texts_main_text(ltexts_resume, ltext_description):
    return f"{ltext_description} settings\n{ltexts_resume}\n\nUse the buttons below to read/edit/delete a language's {ltext_description}:"


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_set_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"set language button {utilities.log(update)}")
    selected_language = context.matches[0].group(1)
    user.selected_language = selected_language

    await update.callback_query.edit_message_text(
        f"Your language has been set to {LANGUAGES[user.selected_language]['emoji']}\nUse the buttons below to change language:",
        reply_markup=get_all_languages_reply_markup(selected_language)
    )


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_set_language_button_start(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"set language button (from /start) {utilities.log(update)}")
    selected_language = context.matches[0].group(1)
    user.selected_language = selected_language

    await update.callback_query.answer(f"language set to {LANGUAGES[user.selected_language]['emoji']}", show_alert=False)

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)

    welcome_text = texts.get_localized_text(session, LocalizedTextKey.WELCOME, language_code)
    welcome_texts = texts.get_texts(session, LocalizedTextKey.WELCOME).all()
    reply_markup = get_start_reply_markup(language_code, welcome_texts)

    text = replace_placeholders(welcome_text.value, update.effective_user)

    await update.effective_message.edit_text(text, reply_markup=reply_markup)

    user.set_started()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"/start {utilities.log(update)}")

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)

    welcome_text = texts.get_localized_text_with_fallback(session, LocalizedTextKey.WELCOME, language_code)
    welcome_texts = texts.get_texts(session, LocalizedTextKey.WELCOME).all()
    reply_markup = get_start_reply_markup(welcome_text.language, welcome_texts)

    text = replace_placeholders(welcome_text.value, update.effective_user)
    await update.message.reply_text(text, reply_markup=reply_markup)

    user.set_started()
    user.update_metadata(update.effective_user)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"/lang {utilities.log(update)}")

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)
    reply_markup = get_all_languages_reply_markup(language_code)

    text = f"Your current language is {LANGUAGES[language_code]['emoji']}\nUse the buttons below to change language:"
    await update.effective_message.reply_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"new user message {utilities.log(update)}")

    user.update_metadata(update.effective_user)

    if user.banned:
        logger.info(f"ignoring user message because the user was banned (shadowban: {user.shadowban})")
        if not user.shadowban:
            reason = user.banned_reason or "not provided"
            await update.message.reply_text(f"{Emoji.BANNED} You were banned from using this bot. Reason: {utilities.escape_html(reason)}")
        return

    chat: Chat = chats.get_staff_chat(session)
    if not chat:
        logger.warning("there is no staff chat set as default")
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
        user_language = get_language_code(user.selected_language, update.effective_user.language_code)
        logger.info(f"sending 'sent to staff' message (user language: {user_language})...")
        try:
            sent_to_staff = texts.get_localized_text_with_fallback(session, LocalizedTextKey.SENT_TO_STAFF, user_language, raise_if_no_fallback=True)
            text = sent_to_staff.value
        except ValueError as e:
            logger.error(f"{e}")
            text = "<i>delivered</i>"

        await update.message.reply_text(text, quote=True)

    user.set_started()
    user.update_last_message()


async def on_chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{update.effective_chat.id}")


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_placeholders_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/placeholders {utilities.log(update)}")

    text = ""
    for placeholder, _ in PLACEHOLDER_REPLACEMENTS.items():
        text += "• <code>{" + placeholder + "}</code>\n"

    text += "\nHold on a placeholder to copy quickly it"

    await update.message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/settings {utilities.log(update)}")

    all_settings = settings.get_settings(session)
    text = ""
    setting: BotSetting
    for setting in all_settings.scalars():
        text += f"•• [<code>{setting.value_type}</code>] <code>{setting.key}</code> -{utilities.escape_html('>')} {setting.value_pretty()}\n" \
                f"• <i>{BOT_SETTINGS_DEFAULTS[setting.key]['description']}</i>\n\n"

    text += "\nTo change a setting, use <code>/set [setting] [new value]</code>\n" \
            "For settings of type <code>bool</code>, you can also use the <code>/enable</code> or " \
            "<code>/disable</code> commands: <code>/enable [setting]</code>\n\n" \
            "Examples:\n" \
            "• <code>/set broadcast_edits false</code>\n" \
            "• <code>/enable sent_to_staff_message</code>\n\n" \
            "Settings of type <code>bool</code> can be changed using the values " \
            "'true' and 'false', 'none' or 'null' can be used to set a setting to <code>NULL</code>\n" \
            "<code>int</code>, <code>float</code>, <code>str</code>, <code>datetime</code> and <code>date</code> " \
            "are auto-detected"

    await update.message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_enable_disable_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/enable or /disable {utilities.log(update)}")

    command = re.search(r"^.(enable|disable).*", update.message.text, re.I).group(1).lower()

    try:
        key = context.args[0].lower()
    except IndexError:
        await update.message.reply_text(f"Usage: <code>/{command} [setting]</code>\nUse /settings for a list of settings. "
                                        f"Only <code>bool</code> settings can be enabled/disabled")
        return

    if key not in BOT_SETTINGS_DEFAULTS:
        await update.message.reply_text(f"<code>{key}</code> is not a recognized setting")
        return

    value = True if command == "enable" else False

    logger.info(f"new value for {key}: {value}")

    setting = settings.get_or_create(session, key, value=value)
    if setting.value_type != ValueType.BOOL:
        await update.message.reply_text(f"<code>{key}</code> is not a boolean setting that can be enabled/disabled")
        return

    setting.update_value(value)
    session.add(setting)

    text = f"<code>{key}</code> {command}d"
    await update.message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/set {utilities.log(update)}")

    try:
        key = context.args[0].lower()
        value = context.args[1]
    except IndexError:
        await update.message.reply_text(f"Usage: <code>/set [setting] [value]</code>\nUse /settings for a list of settings")
        return

    if key not in BOT_SETTINGS_DEFAULTS:
        await update.message.reply_text(f"<code>{key}</code> is not a recognized setting")
        return

    value = utilities.convert_string_to_value(value)

    setting = settings.get_or_create(session, key, value=value)
    session.add(setting)

    text = f"New value for <code>{key}</code>: {setting.value_pretty()}"
    await update.message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/welcome {utilities.log(update)}")

    welcome_text = utilities.get_argument("welcome", update.effective_message.text_html)
    if not welcome_text:
        callback_data_prefix = "getwelcome"
        text = f"Select the language you want to get the welcome message of:"
    else:
        callback_data_prefix = "setwelcome"
        context.user_data["welcome_text"] = welcome_text
        text = f"Select the language for this welcome text:"

    keyboard = [[]]
    for language_code, language_data in LANGUAGES.items():
        keyboard[0].append(InlineKeyboardButton(language_data["emoji"], callback_data=f"{callback_data_prefix}:{language_code}"))
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/help {utilities.log(update)}")

    staff_chat: Chat = chats.get_staff_chat(session)
    if not staff_chat.is_user_admin(update.effective_user.id):
        logger.debug("user is not admin")
        return await on_start_command(update, context)

    await update.message.reply_text(ADMIN_HELP)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_setwelcome_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"setting welcome for language: %s", update.callback_query.data)
    selected_language = context.matches[0].group(1)

    chat: Chat = chats.get_staff_chat(session)
    if not chat:
        logger.warning("there is no staff chat set as default")
        await update.effective_message.edit_text("There's no staff chat set. Add me to the chat and use "
                                                 "<code>/setstaff</code> to set that chat as default staff chat")
        return

    welcome_text = texts.get_localized_text(
        session,
        key=LocalizedTextKey.WELCOME,
        language=selected_language,
        create_if_missing=True
    )

    welcome_text_from_user_data = context.user_data.get("welcome_text")
    welcome_text.value = welcome_text_from_user_data
    welcome_text.updated_by = update.effective_user.id

    await update.effective_message.edit_text(f"Welcome text set for {LANGUAGES[selected_language]['emoji']}:")
    await update.effective_message.reply_text(f"{welcome_text.value}", quote=False)

    user.set_started()


@decorators.catch_exception()
@decorators.pass_session()
async def on_getwelcome_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"getting welcome for language: %s", update.callback_query.data)
    selected_language = context.matches[0].group(1)
    language_emoji = LANGUAGES[selected_language]['emoji']

    welcome_text = texts.get_localized_text(
        session,
        key=LocalizedTextKey.WELCOME,
        language=selected_language,
        create_if_missing=False
    )
    if not welcome_text:
        await update.effective_message.edit_text(f"There's no welcome message for {language_emoji}. "
                                                 f"Use <code>/welcome [welcome message]</code> to set it")
        return

    keyboard = [[
        InlineKeyboardButton("🗑 forget", callback_data=f"unsetwelcome:{selected_language}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.edit_text(f"Welcome text for {language_emoji}:")
    await update.effective_message.reply_text(f"{welcome_text.value}", reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_unsetwelcome_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"deleting welcome for language: %s", update.callback_query.data)
    selected_language = context.matches[0].group(1)
    language_emoji = LANGUAGES[selected_language]['emoji']

    welcome_text = texts.get_localized_text(
        session,
        key=LocalizedTextKey.WELCOME,
        language=selected_language,
        create_if_missing=False
    )
    if welcome_text:
        session.delete(welcome_text)

    await update.effective_message.edit_text(f"Welcome text for {language_emoji} deleted")


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_edited_message_staff(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"message edit in a group {utilities.log(update)}")
    if not settings.get_or_create(session, BotSettingKey.BROADCAST_EDITS).value():
        logger.info("message edits are disabled")
        return

    if not chat.default:
        logger.info(f"ignoring edited message update: chat is not the current staff chat")
        return

    admin_message: AdminMessage = session.query(AdminMessage).filter(
        AdminMessage.chat_id == update.effective_chat.id,
        AdminMessage.message_id == update.effective_message.message_id
    ).one_or_none()
    if not admin_message:
        logger.info(f"couldn't find edited message in the db")
        return

    logger.info(f"editing message {admin_message.reply_message_id} in chat {admin_message.user_message.user_id}")
    await context.bot.edit_message_text(
        chat_id=admin_message.user_message.user_id,
        message_id=admin_message.reply_message_id,
        text=update.effective_message.text_html
    )


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_edited_message_user(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.error("user-sent messages cannot be edited because they are forwarded")

    logger.info(f"message edit in a private chat {utilities.log(update)}")
    if not config.settings.broadcast_message_edits:
        return

    user_message: UserMessage = session.query(UserMessage).filter(
        UserMessage.message_id == update.effective_message.message_id
    ).one_or_none()
    if not user_message:
        logger.info(f"couldn't find edited message in the db")
        return

    logger.info(f"editing message {user_message.forwarded_message_id} in chat {user_message.forwarded_chat_id}")
    await context.bot.edit_message_text(
        chat_id=user_message.forwarded_chat_id,
        message_id=user_message.forwarded_message_id,
        text=update.effective_message.text_html
    )


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_bot_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"reply to a bot message {utilities.log(update)}")

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    await context.bot.send_chat_action(user_message.user_id, ChatAction.TYPING)
    # time.sleep(3)

    sent_message = await update.message.copy(
        chat_id=user_message.user_id,
        reply_to_message_id=user_message.message_id
    )

    user_message.add_reply()
    session.commit()

    admin_message = AdminMessage(
        message_id=update.effective_message.id,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        user_message_id=user_message.message_id,
        reply_message_id=sent_message.message_id,
        message_datetime=update.effective_message.date
    )
    session.add(admin_message)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_admin_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"reply to an admin message starting by ++ {utilities.log(update)}")

    if update.message.reply_to_message.from_user.id == context.bot.id:
        await update.message.reply_text("⚠️ <i>please reply to the admin message you want "
                                        "to reply to</i>")
        return

    admin_message: AdminMessage = admin_messages.get_admin_message(session, update)
    if not admin_message:
        logger.warning(f"couldn't find replied-to admin message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        await update.message.reply_text(
            "⚠️ <i>can't find the message to reply to in the database</i>",
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        return

    await context.bot.send_chat_action(admin_message.user_message.user_id, ChatAction.TYPING)
    # time.sleep(3)

    sent_message = await context.bot.send_message(
        chat_id=admin_message.user_message.user_id,
        text=re.sub(r"^\+\+\s*", "", update.effective_message.text_html),
        reply_to_message_id=admin_message.reply_message_id  # reply to the admin message we previously sent in the chat
    )

    admin_message = AdminMessage(
        message_id=update.effective_message.id,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,  # admin's user_id
        user_message_id=admin_message.user_message.message_id,  # root user message that generated the admins' replies chain
        reply_message_id=sent_message.message_id,
        message_datetime=update.effective_message.date
    )
    session.add(admin_message)

    admin_message.user_message.add_reply()


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_setstaff_command(update: Update, _, session: Session, chat: Chat):
    logger.info(f"/setstaff {utilities.log(update)}")

    if not utilities.is_admin(update.effective_user):
        logger.warning(f"user {update.effective_user.id} ({update.effective_user.full_name}) tried to use /setstaff")
        return

    if "ssilent" in update.message.text.lower():
        # noinspection PyBroadException
        try:
            await update.message.delete()
        except:
            pass

    session.execute(sqlalchemy_update(Chat).values(default=False))
    session.commit()

    chat.default = True
    if "ssilent" not in update.message.text.lower():
        await update.message.reply_text("This group has been set as staff chat")

    session.commit()  # make sure to commit now, just in case something unexpected happens while saving admins

    logger.info("saving administrators...")
    administrators: Tuple[ChatMember] = await update.effective_chat.get_administrators()
    chats.update_administrators(session, chat, administrators)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_reloadadmins_command(update: Update, _, session: Session, chat: Chat):
    logger.info(f"/reloadadmins {utilities.log(update)}")

    logger.info("saving administrators...")
    administrators: Tuple[ChatMember] = await update.effective_chat.get_administrators()
    chats.update_administrators(session, chat, administrators)

    await update.effective_message.reply_text(f"Saved {len(administrators)} administrators")


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"/unban {utilities.log(update)}")

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    user_message.user.unban()
    await update.effective_message.reply_text(f"User unbanned")


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"/ban or /shadowban {utilities.log(update)}")

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    logger.info("banning user...")
    reason = utilities.get_argument(["ban", "shadowban"], update.message.text) or None
    shadowban = bool(re.search(rf"[{COMMAND_PREFIXES}]shadowban", update.message.text, re.I))

    user_message.user.ban(reason=reason, shadowban=shadowban)

    text = f"User {utilities.escape_html(user_message.user.name)} {'shadow' if shadowban else ''}banned, reason: {reason or '-'}\n" \
           f"#id{user_message.user.user_id}"

    await update.effective_message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session()
async def on_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/info {utilities.log(update)}")

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    text = f"• <b>name</b>: {helpers.mention_html(user_message.user.user_id, utilities.escape_html(user_message.user.name))}\n" \
           f"• <b>username</b>: @{user_message.user.username or '-'}\n" \
           f"• <b>first seen</b>: {user_message.user.started_on}\n" \
           f"• <b>last seen</b>: {user_message.user.last_message}\n" \
           f"• <b>language code (telegram)</b>: {user_message.user.language_code}\n" \
           f"• <b>selected language</b>: {user_message.user.selected_language}"

    if user_message.user.banned:
        text += f"\n• <b>banned</b>: {user_message.user.banned} (shadowban: {user_message.user.shadowban})\n" \
                f"• <b>reason</b>: {user_message.user.banned_reason}\n" \
                f"• <b>banned on</b>: {user_message.user.banned_on}" \

    text += f"\n• #id{user_message.user.user_id}"

    await update.effective_message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_revoke_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/revoke (admin) {utilities.log(update)}")

    if update.message.reply_to_message.from_user.id == context.bot.id:
        await update.message.reply_text("⚠️ <i>please reply to the staff message you want "
                                        "to be deleted from the user's chat with the bot</i>")
        return

    admin_message: AdminMessage = admin_messages.get_admin_message(session, update)
    if not admin_message:
        logger.warning(f"couldn't find replied-to admin message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        await update.message.reply_text(
            "⚠️ <i>can't find the message to revoke in the database</i>",
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        return

    logger.info(f"revoking message_id {admin_message.reply_message_id} in chat_id {admin_message.user_message.user.user_id}")
    await context.bot.delete_message(
        chat_id=admin_message.user_message.user.user_id,
        message_id=admin_message.reply_message_id
    )

    await update.message.reply_text(
        "🚮 <i>message revoked successfully: it has been deleted from the user's chat</i>",
        reply_to_message_id=update.message.reply_to_message.message_id
    )

    admin_message.revoke(revoked_by=update.effective_user.id)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_revoke_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/revoke (user) {utilities.log(update)}")

    if not settings.get_or_create(session, BotSettingKey.ALLOW_USER_REVOKE).value():
        logger.info("user revoke is not allowed")
        return

    if not update.message.reply_to_message or update.message.reply_to_message.from_user.id != update.effective_user.id:
        await update.message.reply_text("⚠️ <i>please reply to the message you want to be deleted from the staff's chat</i>")
        return

    user_message: UserMessage = user_messages.get_user_message_by_id(session, update.message.reply_to_message.message_id)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, message_id: {update.message.reply_to_message.message_id}")
        await update.message.reply_text(
            "⚠️ <i>can't find the message to revoke in the database</i>",
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        return

    logger.info(f"revoking message_id {user_message.forwarded_message_id} in staff chat_id {user_message.forwarded_chat_id}")
    await context.bot.delete_message(
        chat_id=user_message.forwarded_chat_id,
        message_id=user_message.forwarded_message_id
    )

    await update.message.reply_text(
        "🚮 <i>message revoked successfully: it has been deleted from the staff chat</i>",
        reply_to_message_id=update.message.reply_to_message.message_id
    )

    user_message.revoke()
    user_message.user.set_started()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_new_group_chat(update: Update, context: CallbackContext, session: Session, user: User, chat: Chat):
    logger.info(f"new group chat {utilities.log(update)}")

    if not utilities.is_admin(update.effective_user):
        logger.info("unauthorized: leaving...")
        await update.effective_chat.leave()
        chat.set_left()
        return

    chat.left = False  # override, it might be True if the chat was previously set

    session.commit()  # make sure to commit now, just in case something unexpected happens while saving admins

    logger.info("saving administrators...")
    administrators: Tuple[ChatMember] = await update.effective_chat.get_administrators()
    chats.update_administrators(session, chat, administrators)

    administrator: ChatMemberAdministrator
    for administrator in administrators:
        if administrator.user.id == context.bot.id:
            chat.set_as_administrator(administrator.can_delete_messages)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_chat_member_update(update: Update, _, session: Session, chat: Chat):
    logger.info(f"chat member update {utilities.log(update)}")

    if update.my_chat_member:
        logger.info(f"MyChatMember update, new status: {update.my_chat_member.new_chat_member.status}")
        if isinstance(update.my_chat_member.new_chat_member, ChatMemberAdministrator):
            chat.set_as_administrator(update.my_chat_member.new_chat_member.can_delete_messages)
        elif isinstance(update.my_chat_member.new_chat_member, (ChatMemberMember, ChatMemberRestricted)):
            chat.unset_as_administrator()
        elif isinstance(update.my_chat_member.new_chat_member, (ChatMemberLeft, ChatMemberBanned)):
            chat.set_left()

    new_chat_member: ChatMember = update.chat_member.new_chat_member if update.chat_member else update.my_chat_member.new_chat_member
    old_chat_member: ChatMember = update.chat_member.old_chat_member if update.chat_member else update.my_chat_member.old_chat_member
    user_id = new_chat_member.user.id

    if old_chat_member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER) and new_chat_member.status not in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
        # user was demoted
        chat_administrator = chat.get_administrator(user_id)
        if chat_administrator:
            session.delete(chat_administrator)
            logger.info(f"user was demoted: deleted db record")
        else:
            logger.info("user was demoted, but there's no record to delete")
    elif new_chat_member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
        # user was promoted/their admin permissions changed
        # noinspection PyTypeChecker
        new_chat_member_dict = chat_member_to_dict(new_chat_member, update.effective_chat.id)
        chat_administrator = ChatAdministrator(**new_chat_member_dict)
        session.merge(chat_administrator)
        logger.info("user was promoted or their admin permissions changed: updated/inserted db record")


def get_localized_text_keyboard(setting_key):
    keyboard = [
        [InlineKeyboardButton("read:", callback_data=f"ls:{setting_key}:helper:read")],
        [InlineKeyboardButton("edit:", callback_data=f"ls:{setting_key}:helper:edit")],
        [InlineKeyboardButton("delete:", callback_data=f"ls:{setting_key}:helper:delete")],
    ]
    for i, action in enumerate(("read", "edit", "delete")):
        for lang_code, lang_data in LANGUAGES.items():
            keyboard[i].append(InlineKeyboardButton(lang_data["emoji"], callback_data=f"ls:{setting_key}:{action}:{lang_code}"))

    return keyboard


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_localized_text_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"localized text settings command ({update.effective_message.text}) {utilities.log(update)}")

    command = utilities.get_command(update.effective_message.text)
    ltext_key = LOCALIZED_TEXTS_TRIGGERS.get(command.lower(), None)
    if not ltext_key:
        logger.warning(f"couldn't find setting ltext_key for command \"{command}\"")
        return

    ltext_description = LOCALIZED_TEXTS_DESCRIPTION[ltext_key]

    reply_markup = InlineKeyboardMarkup(get_localized_text_keyboard(ltext_key))
    settings_resume = get_localized_text_resume_text(session, ltext_key)
    text = get_localized_texts_main_text(settings_resume, ltext_description)
    sent_message = await update.message.reply_text(text, reply_markup=reply_markup)

    # save this emssage's message_id and remove the last message's keyboard
    remove_keyboard_message_id = context.user_data.get(TempDataKey.LOCALIZED_TEXTS_LAST_MESSAGE_ID, None)
    if remove_keyboard_message_id:
        await context.bot.edit_message_reply_markup(update.effective_user.id, remove_keyboard_message_id, reply_markup=None)
    context.user_data[TempDataKey.LOCALIZED_TEXTS_LAST_MESSAGE_ID] = sent_message.message_id


def get_sent_to_staff_keyboard(current_status) -> InlineKeyboardMarkup:
    if current_status and current_status == "true":
        stt_button = InlineKeyboardButton("disable", callback_data=f"{BotSettingKey.SENT_TO_STAFF}:disable")
    else:
        stt_button = InlineKeyboardButton("enable", callback_data=f"{BotSettingKey.SENT_TO_STAFF}:enable")

    keyboard = get_localized_text_keyboard(LocalizedTextKey.SENT_TO_STAFF)
    # add a bottun as the first line to quickly enable/disable the message
    keyboard.insert(0, [
        stt_button
    ])

    return InlineKeyboardMarkup(keyboard)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_senttostaff_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/senttostaff command {utilities.log(update)})")

    stt_status = settings.get_or_create(session, BotSettingKey.SENT_TO_STAFF)
    reply_markup = get_sent_to_staff_keyboard(stt_status.value)
    await update.message.reply_text("\"sent to staff\" message settings. Select what you want to do:", reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_localized_text_helper_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized setting helper from {utilities.log(update)}")
    ltext_key = context.matches[0].group(1)
    action = context.matches[0].group(2)

    ltext_description = LOCALIZED_TEXTS_DESCRIPTION[ltext_key]

    helper_tips = {
        "read": f"tap on the language's flag to read the currently set {ltext_description}",
        "edit": f"tap on the language's flag to edit that language's {ltext_description}",
        "delete": f"tap on the language's flag to delete that language's {ltext_description}. "
                  f"Users who selected that language will receive the fallback language's {ltext_description} (en)",
    }

    await update.callback_query.answer(helper_tips[action], show_alert=True, cache_time=CACHE_TIME)


@decorators.catch_exception()
@decorators.pass_session()
async def on_localized_text_read_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized text read {utilities.log(update)}")
    ltext_key = context.matches[0].group(1)
    language = context.matches[0].group(2)
    language_emoji = LANGUAGES[language]["emoji"]
    ltext_description = LOCALIZED_TEXTS_DESCRIPTION[ltext_key]

    ltext = texts.get_localized_text(
        session,
        key=ltext_key,
        language=language,
        create_if_missing=False
    )
    if not ltext:
        await update.callback_query.answer(f"There's no {ltext_description} set for {language_emoji}")
        return

    reply_markup = InlineKeyboardMarkup(get_localized_text_keyboard(ltext_key))
    text = f"Current {ltext_description} for {language_emoji}:\n\n{ltext.value}"
    await utilities.edit_text_safe(update, text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_localized_text_delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized text delete {utilities.log(update)}")
    ltext_key = context.matches[0].group(1)
    language = context.matches[0].group(2)

    language_emoji = LANGUAGES[language]["emoji"]
    ltext_description = LOCALIZED_TEXTS_DESCRIPTION[ltext_key]

    ltext = texts.get_localized_text(
        session,
        key=ltext_key,
        language=language,
        create_if_missing=False
    )
    if ltext:
        session.delete(ltext)

    reply_markup = InlineKeyboardMarkup(get_localized_text_keyboard(ltext_key))
    ltexts_resume = get_localized_text_resume_text(session, ltext_key)
    text = get_localized_texts_main_text(ltexts_resume, ltext_description)
    await update.callback_query.answer(f"{ltext_description} deleted for {language_emoji}")
    await utilities.edit_text_safe(update, text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_localized_text_edit_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized text edit {utilities.log(update)}")
    ltext_key = context.matches[0].group(1)
    language = context.matches[0].group(2)

    language_emoji = LANGUAGES[language]["emoji"]
    ltext_description = LOCALIZED_TEXTS_DESCRIPTION[ltext_key]

    context.user_data[TempDataKey.LOCALIZED_TEXTS] = dict(key=ltext_key, lang=language)
    await update.effective_message.edit_text(f"Please send me the new {ltext_description} text for {language_emoji} "
                                             f"(or use /cancel to cancel):")

    return State.WAITING_NEW_LOCALIZED_TEXT


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_localized_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"received new localized text {utilities.log(update)})")

    ltext_data = context.user_data.pop(TempDataKey.LOCALIZED_TEXTS)
    ltext_key = ltext_data["key"]
    ltext_language = ltext_data["lang"]

    ltext_description = LOCALIZED_TEXTS_DESCRIPTION[ltext_key]
    lang_emoji = LANGUAGES[ltext_language]['emoji']

    ltext = texts.get_localized_text(
        session,
        key=ltext_key,
        language=ltext_language,
        create_if_missing=True
    )
    ltext.value = update.effective_message.text_html
    ltext.updated_by = update.effective_user.id

    reply_markup = InlineKeyboardMarkup(get_localized_text_keyboard(ltext_key))
    await update.effective_message.reply_text(f"{ltext_description} set for {lang_emoji}:\n\n{ltext.value}")

    ltexts_resume = get_localized_text_resume_text(session, ltext_key)
    text = get_localized_texts_main_text(ltexts_resume, ltext_description)
    await update.effective_message.reply_text(text, reply_markup=reply_markup)

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_welcome_receive_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"(unexpected) received new welcome message {utilities.log(update)}")

    await update.message.reply_text("Please send me the new welcome message for the selected language")

    return State.WAITING_NEW_LOCALIZED_TEXT


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_localized_text_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"waiting new localized text: /cancel command {utilities.log(update)}")

    context.user_data.pop(TempDataKey.LOCALIZED_TEXTS, None)

    await update.effective_message.reply_text("Okay, operation canceled :)")

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_localized_text_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"waiting for new localized text: timed out")

    ltext_data = context.user_data.pop(TempDataKey.LOCALIZED_TEXTS, None)
    ltext_description = LOCALIZED_TEXTS_DESCRIPTION[ltext_data['key']]

    await update.effective_message.reply_text(f"Okay, it looks like you forgot... "
                                              f"I'm exiting the {ltext_description} configuration")

    return ConversationHandler.END


async def post_init(application: Application) -> None:
    bot: ExtBot = application.bot

    await bot.set_my_commands(
        [BotCommand("start", "see the welcome message"), BotCommand("lang", "set your language")],
        scope=BotCommandScopeAllPrivateChats()
    )
    await bot.set_my_commands(
        [BotCommand("start", "messaggio di benvenuto"), BotCommand("lang", "cambia lingua")],
        language_code=Language.IT,
        scope=BotCommandScopeAllPrivateChats()
    )
    await bot.set_my_commands(
        [BotCommand("start", "mensaje de bienvenida"), BotCommand("lang", "cambiar idioma")],
        language_code=Language.ES,
        scope=BotCommandScopeAllPrivateChats()
    )
    await bot.set_my_commands(
        [BotCommand("start", "message d'accueil"), BotCommand("lang", "changer langue")],
        language_code=Language.FR,
        scope=BotCommandScopeAllPrivateChats()
    )

    session: Session = get_session()

    logger.info("populating default settings...")
    for bot_setting_key, bot_setting_data in BOT_SETTINGS_DEFAULTS.items():
        setting = session.query(BotSetting).filter(BotSetting.key == bot_setting_key).one_or_none()
        if not setting:
            setting = BotSetting(bot_setting_key, bot_setting_data["default"])
            session.add(setting)

    session.commit()

    staff_chat = chats.get_staff_chat(session)
    if not staff_chat:
        return

    staff_chat_chat_member: ChatMember = await bot.get_chat_member(staff_chat.chat_id, bot.id)
    if not isinstance(staff_chat_chat_member, ChatMemberAdministrator):
        logger.info(f"not an admin in the staff chat {staff_chat.chat_id}, current status: {staff_chat_chat_member.status}")
        staff_chat.unset_as_administrator()
    else:
        logger.info(f"admin in the staff chat {staff_chat.chat_id}, can_delete_messages: {staff_chat_chat_member.can_delete_messages}")
        staff_chat.set_as_administrator(staff_chat_chat_member.can_delete_messages)

    session.add(staff_chat)
    session.commit()


def main():
    utilities.load_logging_config('logging.json')

    app: Application = ApplicationBuilder() \
        .token(config.telegram.token) \
        .defaults(defaults) \
        .post_init(post_init) \
        .build()

    class FilterReplyToBot(MessageFilter):
        def filter(self, message):
            if message.reply_to_message and message.reply_to_message.from_user:
                return message.reply_to_message.from_user.id == app.bot.id

    class NewGroup(MessageFilter):
        def filter(self, message):
            if message.new_chat_members:
                member: TelegramUser
                for member in message.new_chat_members:
                    if member.id == app.bot.id:
                        return True

    new_group = NewGroup()
    filter_reply_to_bot = FilterReplyToBot()

    # edited messages NEED to be catched before anything else, otherwise they will procedded by other MessageHandlers
    # app.add_handler(TypeHandler(Update.EDITED_MESSAGE, on_edited_message))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT & filters.ChatType.GROUPS, on_edited_message_staff))
    # user messages acnnot be edited because they are forwarded
    # app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT & filters.ChatType.PRIVATE, on_edited_message_user))

    # private chat: admins
    # app.add_handler(CommandHandler('welcome', on_welcome_command, filters.ChatType.PRIVATE))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['settings', 's'], on_settings_command, filters.ChatType.PRIVATE))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['set'], on_set_command, filters.ChatType.PRIVATE))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['enable', 'disable'], on_enable_disable_command, filters.ChatType.PRIVATE))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['placeholders', 'ph'], on_placeholders_command, filters.ChatType.PRIVATE))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['welcome', 'w', 'senttostaff', 'sts'], on_localized_text_settings_command, filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_localized_text_helper_button, rf"ls:(.+):helper:(.*)"))
    app.add_handler(CallbackQueryHandler(on_localized_text_read_button, rf"ls:(.+):read:(.*)"))
    app.add_handler(CallbackQueryHandler(on_localized_text_delete_button, rf"ls:(.+):delete:(.*)"))
    edit_welcome_conversation_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(on_localized_text_edit_button, rf"ls:(.+):edit:(.*)")],
        states={
            State.WAITING_NEW_LOCALIZED_TEXT: [
                PrefixHandler(COMMAND_PREFIXES, "cancel", on_localized_text_cancel_command),
                MessageHandler(filters.TEXT, on_localized_text_receive),
                MessageHandler(~filters.TEXT, on_welcome_receive_unexpected)
            ],
            ConversationHandler.TIMEOUT: [
                # on timeout, the *last update* is broadcasted to all users. it might be a callback query or a text
                MessageHandler(filters.ALL, on_localized_text_timeout),
                CallbackQueryHandler(on_localized_text_timeout, ".*"),
            ]
        },
        fallbacks=[
            PrefixHandler(COMMAND_PREFIXES, "cancel", on_localized_text_cancel_command)
        ],
        conversation_timeout=30*60
    )
    app.add_handler(edit_welcome_conversation_handler)

    # app.add_handler(CommandHandler('senttostaff', on_senttostaff_settings_command, filters.ChatType.PRIVATE))

    # private chat: mixed
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, 'help', on_help_command, filters.ChatType.PRIVATE))

    # private chat: users
    app.add_handler(CommandHandler('start', on_start_command, filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('lang', on_lang_command, filters.ChatType.PRIVATE))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['revoke', 'del'], on_revoke_user_command, filters.ChatType.PRIVATE))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE, on_user_message))

    # staff chat
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['setstaff', 'ssilent'], on_setstaff_command, filters.ChatType.GROUPS))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, 'reloadadmins', on_reloadadmins_command, filters.ChatType.GROUPS))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['ban', 'shadowban'], on_ban_command, filters.ChatType.GROUPS & filter_reply_to_bot))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, 'unban', on_unban_command, filters.ChatType.GROUPS & filter_reply_to_bot))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, 'info', on_info_command, filters.ChatType.GROUPS & filter_reply_to_bot))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['revoke', 'del'], on_revoke_admin_command, filters.ChatType.GROUPS & filters.REPLY))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.REPLY & filters.Regex(r"^\+\+\s*.+"), on_admin_message_reply))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filter_reply_to_bot, on_bot_message_reply))
    # bot.add_handler(CommandHandler('chatid', on_chatid_command, filters.ChatType.GROUPS))

    # callback query
    app.add_handler(CallbackQueryHandler(on_set_language_button, pattern="^setlang:(..)$"))
    app.add_handler(CallbackQueryHandler(on_set_language_button_start, pattern="^setlangstart:(..)$"))
    app.add_handler(CallbackQueryHandler(on_setwelcome_language_button, pattern="^setwelcome:(..)$"))
    app.add_handler(CallbackQueryHandler(on_getwelcome_language_button, pattern="^getwelcome:(..)$"))
    app.add_handler(CallbackQueryHandler(on_unsetwelcome_language_button, pattern="^unsetwelcome:(..)$"))

    # other
    app.add_handler(MessageHandler(new_group, on_new_group_chat))
    app.add_handler(ChatMemberHandler(on_chat_member_update, ChatMemberHandler.ANY_CHAT_MEMBER))

    logger.info(f"polling for updates...")
    app.run_polling(
        drop_pending_updates=False,
        allowed_updates=[Update.MESSAGE, Update.EDITED_MESSAGE, Update.CALLBACK_QUERY, Update.CHAT_MEMBER, Update.MY_CHAT_MEMBER]
    )


if __name__ == '__main__':
    main()
