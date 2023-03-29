import logging
import re
import time
from typing import Optional, Tuple, List, Union

import pytz
from sqlalchemy.orm import Session
from sqlalchemy import update as sqlalchemy_update, true, ChunkedIteratorResult, select
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberAdministrator, User as TelegramUser, \
    ChatMemberOwner, ChatMember, Message, BotCommand, BotCommandScopeAllPrivateChats
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Defaults, filters, MessageHandler, \
    CallbackQueryHandler, ChatMemberHandler, PrefixHandler, Application, ExtBot, ConversationHandler, TypeHandler
from telegram.ext.filters import MessageFilter
from telegram import helpers

from database import engine
from database.models import User, UserMessage, Chat, Setting, chat_member_to_dict, ChatAdministrator, AdminMessage
from database.queries import settings, chats, user_messages, admin_messages
import decorators
import utilities
from emojis import Emoji
from constants import LANGUAGES, SettingKey, Language, ADMIN_HELP, COMMAND_PREFIXES, State, CACHE_TIME, TempDataKey
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

    return telegram_language_code or "en"


def get_start_reply_markup(user_language: str) -> InlineKeyboardMarkup:
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


def get_localized_setting_resume_text(session: Session, setting_key: str):
    result = settings.get_settings(session, setting_key)
    settings_statuses = {}

    setting: Setting
    for setting in result.scalars():
        settings_statuses[setting.language] = "set" if setting.value else "<b>not set</b>"

    for lang_code, lang_data in LANGUAGES.items():
        if lang_code in settings_statuses:
            continue

        settings_statuses[lang_code] = "<b>not set</b>"

    text = ""
    for lang_code, current_status in settings_statuses.items():
        text += f"\n{LANGUAGES[lang_code]['emoji']} -> {current_status}"

    return text.strip()


def get_welcome_settings_main_text(settings_resume):
    return f"Welcome message settings\n{settings_resume}\n\nUse the buttons below to read/edit/delete a language's welcome message:"


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_set_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"set language button {utilities.log(update)}")
    selected_language = context.matches[0].group(1)
    user.selected_language = selected_language

    await update.callback_query.answer(f"langauge set to {LANGUAGES[user.selected_language]['emoji']}", show_alert=False)

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)
    reply_markup = get_start_reply_markup(language_code)

    # also update the welcome text
    welcome_setting = settings.get_localized_setting(session, SettingKey.WELCOME, language_code)
    text = replace_placeholders(welcome_setting.value, update.effective_user)

    await update.effective_message.edit_text(text, reply_markup=reply_markup)

    user.set_started()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"/start {utilities.log(update)}")

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)

    welcome_setting = settings.get_localized_setting(session, SettingKey.WELCOME, language_code)

    reply_markup = get_start_reply_markup(language_code)

    text = replace_placeholders(welcome_setting.value, update.effective_user)
    await update.message.reply_text(text, reply_markup=reply_markup)

    user.set_started()
    user.update_metadata(update.effective_user)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"/lang {utilities.log(update)}")

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)
    reply_markup = get_start_reply_markup(language_code)

    text = f"Your current language is {LANGUAGES[language_code]['emoji']}. Use the buttons below to change language:"
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

    await update.message.reply_text("<i>Message sent to the staff, now wait for an admin's reply. "
                                    "Please be aware that it might take some time</i> :)", quote=True)

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
    for langauge_code, language_data in LANGUAGES.items():
        keyboard[0].append(InlineKeyboardButton(language_data["emoji"], callback_data=f"{callback_data_prefix}:{langauge_code}"))
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/help {utilities.log(update)}")

    staff_chat: Chat = chats.get_staff_chat(session)
    if not staff_chat.is_admin(update.effective_user.id):
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

    setting = settings.get_setting(
        session,
        key=SettingKey.WELCOME,
        language=selected_language,
        create_if_missing=True
    )

    welcome_text = context.user_data.get("welcome_text")
    setting.value = welcome_text
    setting.updated_by = update.effective_user.id

    await update.effective_message.edit_text(f"Welcome text set for {LANGUAGES[selected_language]['emoji']}:")
    await update.effective_message.reply_text(f"{setting.value}", quote=False)

    user.set_started()


@decorators.catch_exception()
@decorators.pass_session()
async def on_getwelcome_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"getting welcome for language: %s", update.callback_query.data)
    selected_language = context.matches[0].group(1)
    langauge_emoji = LANGUAGES[selected_language]['emoji']

    setting = settings.get_setting(
        session,
        key=SettingKey.WELCOME,
        language=selected_language,
        create_if_missing=False
    )
    if not setting:
        await update.effective_message.edit_text(f"There's no welcome message for {langauge_emoji}. "
                                                 f"Use <code>/welcome [welcome message]</code> to set it")
        return

    keyboard = [[
        InlineKeyboardButton("🗑 forget", callback_data=f"unsetwelcome:{selected_language}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.edit_text(f"Welcome text for {langauge_emoji}:")
    await update.effective_message.reply_text(f"{setting.value}", reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_unsetwelcome_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"deleting welcome for language: %s", update.callback_query.data)
    selected_language = context.matches[0].group(1)
    langauge_emoji = LANGUAGES[selected_language]['emoji']

    setting = settings.get_setting(
        session,
        key=SettingKey.WELCOME,
        language=selected_language,
        create_if_missing=False
    )
    if setting:
        session.delete(setting)

    await update.effective_message.edit_text(f"Welcome text for {langauge_emoji} deleted")


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"message edit")
    if not config.settings.broadcast_message_edits:
        return


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

    admin_message: AdminMessage = admin_messages.get_admin_message(session, update)
    if not admin_message:
        logger.warning(f"couldn't find replied-to admin message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        await update.message.reply_text(
            "can't find the message to revoke in the database",
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        return

    logger.info(f"revoking message_id {admin_message.reply_message_id} in chat_id {admin_message.user_message.user.user_id}")
    await context.bot.delete_message(
        chat_id=admin_message.user_message.user.user_id,
        message_id=admin_message.reply_message_id
    )

    await update.message.reply_text(
        "message revoked",
        reply_to_message_id=update.message.reply_to_message.message_id
    )

    admin_message.revoke(revoked_by=update.effective_user.id)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_revoke_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/revoke (user) {utilities.log(update)}")

    if update.message.reply_to_message.from_user.id != update.effective_user.id:
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
        "🚮 <i>message revoked successfully</i>",
        reply_to_message_id=update.message.reply_to_message.message_id
    )

    user_message.revoke()
    user_message.user.set_started()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_new_group_chat(update: Update, _, session: Session, user: User, chat: Chat):
    logger.info(f"new group chat {utilities.log(update)}")

    if not utilities.is_admin(update.effective_user):
        logger.info("unauthorized: leaving...")
        await update.effective_chat.leave()
        chat.left = True
        return

    chat.left = False  # override, it might be True if the chat was previously set

    session.commit()  # make sure to commit now, just in case something unexpected happens while saving admins

    logger.info("saving administrators...")
    administrators: Tuple[ChatMember] = await update.effective_chat.get_administrators()
    chats.update_administrators(session, chat, administrators)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_chat_member_update(update: Update, _, session: Session, chat: Chat):
    logger.info(f"chat member update {utilities.log(update)}")

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


def get_localized_settings_keyboard(setting_key):
    keyboard = [
        [InlineKeyboardButton("read:", callback_data=f"{setting_key}:helper:read")],
        [InlineKeyboardButton("edit:", callback_data=f"{setting_key}:helper:edit")],
        [InlineKeyboardButton("delete:", callback_data=f"{setting_key}:helper:delete")],
    ]
    for i, action in enumerate(("read", "edit", "delete")):
        for lang_code, lang_data in LANGUAGES.items():
            keyboard[i].append(InlineKeyboardButton(lang_data["emoji"], callback_data=f"{setting_key}:{action}:{lang_code}"))

    return keyboard


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_welcome_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/welcome command {utilities.log(update)}")

    reply_markup = InlineKeyboardMarkup(get_localized_settings_keyboard(SettingKey.WELCOME))
    settings_resume = get_localized_setting_resume_text(session, SettingKey.WELCOME)
    text = get_welcome_settings_main_text(settings_resume)
    await update.message.reply_text(text, reply_markup=reply_markup)


def get_sent_to_staff_keyboard(current_status) -> InlineKeyboardMarkup:
    if current_status and current_status == "true":
        stt_button = InlineKeyboardButton("disable", callback_data=f"{SettingKey.SENT_TO_STAFF_STATUS}:disable")
    else:
        stt_button = InlineKeyboardButton("enable", callback_data=f"{SettingKey.SENT_TO_STAFF_STATUS}:enable")

    keyboard = get_localized_settings_keyboard(SettingKey.SENT_TO_STAFF)
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

    stt_status = settings.get_setting(session, SettingKey.SENT_TO_STAFF_STATUS)
    reply_markup = get_sent_to_staff_keyboard(stt_status.value)
    await update.message.reply_text("\"sent to staff\" message settings. Select what you want to do:", reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_welcome_helper_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"welcome helper from {utilities.log(update)}")
    action = context.matches[0].group(1)
    helper_tips = {
        "read": "tap on the language's flag to read the currently set welcome message",
        "edit": "tap on the language's flag to edit that language's welcome message",
        "delete": "tap on the language's flag to delete that language's welcome message. "
                  "Users who selected that language will receive the fallback language's welcome message (en)",
    }

    await update.callback_query.answer(helper_tips[action], show_alert=True, cache_time=CACHE_TIME)


@decorators.catch_exception()
@decorators.pass_session()
async def on_welcome_read_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"welcome read {utilities.log(update)}")
    language = context.matches[0].group(1)
    langauge_emoji = LANGUAGES[language]["emoji"]

    setting = settings.get_setting(
        session,
        key=SettingKey.WELCOME,
        language=language,
        create_if_missing=False
    )
    if not setting:
        await update.callback_query.answer(f"There's no welcome message set for {langauge_emoji}")
        return

    reply_markup = InlineKeyboardMarkup(get_localized_settings_keyboard(SettingKey.WELCOME))
    text = f"Current welcome message for {langauge_emoji}:\n\n{setting.value}"
    await utilities.edit_text_safe(update, text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_welcome_delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"welcome delete {utilities.log(update)}")
    language = context.matches[0].group(1)
    langauge_emoji = LANGUAGES[language]["emoji"]

    setting = settings.get_setting(
        session,
        key=SettingKey.WELCOME,
        language=language,
        create_if_missing=False
    )
    if setting:
        session.delete(setting)

    reply_markup = InlineKeyboardMarkup(get_localized_settings_keyboard(SettingKey.WELCOME))
    settings_resume = get_localized_setting_resume_text(session, SettingKey.WELCOME)
    text = get_welcome_settings_main_text(settings_resume)
    await update.callback_query.answer(f"Welcome message deleted for {langauge_emoji}")
    await utilities.edit_text_safe(update, text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_welcome_edit_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"welcome edit {utilities.log(update)}")
    language = context.matches[0].group(1)
    langauge_emoji = LANGUAGES[language]["emoji"]

    context.user_data[TempDataKey.WELCOME_LANGUAGE] = language
    await update.effective_message.edit_text(f"Please send me the new welcome text for {langauge_emoji} "
                                             f"(or use /cancel to cancel):")

    return State.WAITING_WELCOME


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_welcome_receive(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"received new welcome message {utilities.log(update)})")

    language = context.user_data.pop(TempDataKey.WELCOME_LANGUAGE)

    setting = settings.get_setting(
        session,
        key=SettingKey.WELCOME,
        language=language,
        create_if_missing=True
    )
    setting.value = update.effective_message.text_html
    setting.updated_by = update.effective_user.id

    reply_markup = InlineKeyboardMarkup(get_localized_settings_keyboard(SettingKey.WELCOME))
    await update.effective_message.reply_text(f"Welcome text set for {LANGUAGES[language]['emoji']}:\n\n{setting.value}")

    settings_resume = get_localized_setting_resume_text(session, SettingKey.WELCOME)
    text = get_welcome_settings_main_text(settings_resume)
    await update.effective_message.reply_text(text, reply_markup=reply_markup)

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_welcome_receive_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"(unexpected) received new welcome message {utilities.log(update)}")

    await update.message.reply_text("Please send me the new welcome message for the selected language")

    return State.WAITING_WELCOME


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_welcome_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"welcome: /cancel command {utilities.log(update)}")

    context.user_data.pop(TempDataKey.WELCOME_LANGUAGE, None)

    await update.effective_message.reply_text("Okay, operation canceled :)")

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_welcome_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"waiting for welcome text: timed out")

    context.user_data.pop(TempDataKey.WELCOME_LANGUAGE, None)

    await update.effective_message.reply_text("Okay, it looks like you forgot... "
                                              "I'm exiting the welcome message configuration. "
                                              "Use /welcome to open it again")

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
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, on_edited_message))

    # private chat: admins
    # app.add_handler(CommandHandler('welcome', on_welcome_command, filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('placeholders', on_placeholders_command, filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler('welcome', on_welcome_settings_command, filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_welcome_helper_button, rf"{SettingKey.WELCOME}:helper:(.*)"))
    app.add_handler(CallbackQueryHandler(on_welcome_read_button, rf"{SettingKey.WELCOME}:read:(.*)"))
    app.add_handler(CallbackQueryHandler(on_welcome_delete_button, rf"{SettingKey.WELCOME}:delete:(.*)"))
    edit_welcome_conversation_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(on_welcome_edit_button, rf"{SettingKey.WELCOME}:edit:(.*)")],
        states={
            State.WAITING_WELCOME: [
                PrefixHandler(COMMAND_PREFIXES, "cancel", on_welcome_cancel_command),
                MessageHandler(filters.TEXT, on_welcome_receive),
                MessageHandler(~filters.TEXT, on_welcome_receive_unexpected)
            ],
            ConversationHandler.TIMEOUT: [
                # on timeout, the *last update* is broadcasted to all users. it might be a callback query or a text
                MessageHandler(filters.ALL, on_welcome_timeout),
                CallbackQueryHandler(on_welcome_timeout, ".*"),
            ]
        },
        fallbacks=[
            PrefixHandler(COMMAND_PREFIXES, "cancel", on_welcome_cancel_command)
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
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['revoke', 'del'], on_revoke_user_command, filters.ChatType.PRIVATE & filters.REPLY))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE, on_user_message))

    # staff chat
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['setstaff', 'ssilent'], on_setstaff_command, filters.ChatType.GROUPS))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, 'reloadadmins', on_reloadadmins_command, filters.ChatType.GROUPS))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['ban', 'shadowban'], on_ban_command, filters.ChatType.GROUPS & filter_reply_to_bot))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, 'unban', on_unban_command, filters.ChatType.GROUPS & filter_reply_to_bot))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, 'info', on_info_command, filters.ChatType.GROUPS & filter_reply_to_bot))
    app.add_handler(PrefixHandler(COMMAND_PREFIXES, ['revoke', 'del'], on_revoke_admin_command, filters.ChatType.GROUPS & filters.REPLY))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filter_reply_to_bot, on_bot_message_reply))
    # bot.add_handler(CommandHandler('chatid', on_chatid_command, filters.ChatType.GROUPS))

    # callback query
    app.add_handler(CallbackQueryHandler(on_set_language_button, pattern="^setlang:(..)$"))
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
