import logging
import re
from typing import Optional, Tuple, List, Union

import pytz
from sqlalchemy.orm import Session
from sqlalchemy import update as sqlalchemy_update, true
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberAdministrator, User as TelegramUser, \
    ChatMemberOwner, ChatMember, Message
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Defaults, filters, MessageHandler, \
    CallbackQueryHandler, ChatMemberHandler, PrefixHandler
from telegram.ext.filters import MessageFilter
from telegram import helpers

from database.models import User, UserMessage, Chat, Setting, chat_member_to_dict, ChatAdministrator
from database.queries import settings, chats, user_messages
import decorators
import utilities
from emojis import Emoji
from constants import LANGUAGES, SettingKey, Language, ADMIN_HELP, COMMAND_PREFIXES
from config import config

logger = logging.getLogger(__name__)

defaults = Defaults(
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        tzinfo=pytz.timezone('Europe/Rome'),
        quote=False
    )
bot = ApplicationBuilder().token(config.telegram.token).defaults(defaults).build()


class FilterReplyToBot(MessageFilter):
    def filter(self, message):
        if message.reply_to_message and message.reply_to_message.from_user:
            return message.reply_to_message.from_user.id == bot.bot.id


class NewGroup(MessageFilter):
    def filter(self, message):
        if message.new_chat_members:
            member: TelegramUser
            for member in message.new_chat_members:
                if member.id == bot.bot.id:
                    return True


new_group = NewGroup()
filter_reply_to_bot = FilterReplyToBot()


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


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_set_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"user changed language: %s", update.callback_query.data)
    selected_language = context.matches[0].group(1)
    user.selected_language = selected_language

    await update.callback_query.answer(f"langauge set to {LANGUAGES[user.selected_language]['emoji']}", show_alert=False)

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)
    reply_markup = get_start_reply_markup(language_code)

    # also update the welcome text
    welcome_setting = settings.get_welcome(session, language_code)
    text = replace_placeholders(welcome_setting.value, update.effective_user)

    await update.effective_message.edit_text(text, reply_markup=reply_markup)

    user.set_started(update_last_message=True)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"/start from {update.effective_user.id} ({update.effective_user.first_name}) (lang: {update.effective_user.language_code})")

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)

    welcome_setting = settings.get_welcome(session, language_code)

    reply_markup = get_start_reply_markup(language_code)

    text = replace_placeholders(welcome_setting.value, update.effective_user)
    await update.message.reply_text(text, reply_markup=reply_markup)

    user.set_started(update_last_message=True)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"/lang from {update.effective_user.id} ({update.effective_user.first_name}) (lang: {update.effective_user.language_code})")

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)
    reply_markup = get_start_reply_markup(language_code)

    text = f"Your current language is {LANGUAGES[language_code]['emoji']}. Use the buttons below to change language:"
    await update.effective_message.reply_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"new user message from {update.effective_user.id} ({update.effective_user.full_name})")

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
        forwarded_chat_id=config.staff.chat_id,
        forwarded_message_id=forwarded_message.message_id,
        message_datetime=update.effective_message.date
    )
    session.add(user_message)
    user.set_started(update_last_message=True)


async def on_chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{update.effective_chat.id}")


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_placeholders_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/placeholders command from {update.effective_user.id} ({update.effective_user.full_name})")

    text = ""
    for placeholder, _ in PLACEHOLDER_REPLACEMENTS.items():
        text += "• <code>{" + placeholder + "}</code>\n"

    text += "\n\nHold on a placeholder to copy quickly it"

    await update.message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/welcome command from {update.effective_user.id} ({update.effective_user.full_name})")

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
    logger.info(f"/help command from {update.effective_user.id} ({update.effective_user.full_name})")

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

    user.set_started(update_last_message=True)


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
@decorators.pass_session()
async def on_bot_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"reply to a bot message in {update.effective_chat.title} ({update.effective_chat.id})")

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    await update.message.copy(
        chat_id=user_message.user_id,
        reply_to_message_id=user_message.message_id
    )

    user_message.add_reply()


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_setstaff_command(update: Update, _, session: Session, chat: Chat):
    logger.info("/setstaff in %d (%s)", update.effective_chat.id, update.effective_chat.title)

    sqlalchemy_update(Chat).where().values(default=False)
    chat.default = True
    await update.message.reply_text("This group has been set as staff chat")

    session.commit()  # make sure to commit now, just in case something unexpected happens while saving admins

    logger.info("saving administrators...")
    administrators: Tuple[ChatMember] = await update.effective_chat.get_administrators()
    chats.update_administrators(session, chat, administrators)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_reloadadmins_command(update: Update, _, session: Session, chat: Chat):
    logger.info("/reloadadmins in %d (%s)", update.effective_chat.id, update.effective_chat.title)

    logger.info("saving administrators...")
    administrators: Tuple[ChatMember] = await update.effective_chat.get_administrators()
    chats.update_administrators(session, chat, administrators)

    await update.effective_message.reply_text(f"Saved {len(administrators)} administrators")


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info("/unban in %d (%s)", update.effective_chat.id, update.effective_chat.title)

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
    logger.info("/ban or /shadowban in %d (%s)", update.effective_chat.id, update.effective_chat.title)

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
    logger.info("/info in %d (%s)", update.effective_chat.id, update.effective_chat.title)

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    text = f"• <b>name</b>: {helpers.mention_html(user_message.user.user_id, utilities.escape_html(user_message.user.name))}\n" \
           f"• <b>username</b>: @{user_message.user.username or '-'}\n" \
           f"• <b>first seen</b>: {user_message.user.started_on}\n" \
           f"• <b>last seen</b>: {user_message.user.last_message}"

    if user_message.user.banned:
        text += f"\n• <b>banned</b>: {user_message.user.banned} (shadowban: {user_message.user.shadowban})\n" \
                f"• <b>reason</b>: {user_message.user.banned_reason}\n" \
                f"• <b>banned on</b>: {user_message.user.banned_on}" \

    text += f"\n• #id{user_message.user.user_id}"

    await update.effective_message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_new_group_chat(update: Update, _, session: Session, user: User, chat: Chat):
    logger.info("new group chat %d (%s)", update.effective_chat.id, update.effective_chat.title)

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
    logger.info("chat member update")

    new_chat_member: ChatMember = update.chat_member.new_chat_member if update.chat_member else update.my_chat_member.new_chat_member
    old_chat_member: ChatMember = update.chat_member.old_chat_member if update.chat_member else update.my_chat_member.old_chat_member
    user_id = new_chat_member.user.id

    if old_chat_member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER) and new_chat_member.status not in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
        # user was demoted
        chat_administrator = chat.get_administrator(user_id)
        if chat_administrator:
            session.delete(chat_administrator)
            logger.info("chat member: deleted db record")
        else:
            logger.info("no record to delete")
    elif new_chat_member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
        # user was promoted/their admin permissions changed
        new_chat_member_dict = chat_member_to_dict(new_chat_member, update.effective_chat.id)
        chat_administrator = ChatAdministrator(**new_chat_member_dict)
        session.merge(chat_administrator)
        logger.info("chat member: updated/inserted db record")


def main():
    utilities.load_logging_config('logging.json')

    # private chat: admins
    bot.add_handler(CommandHandler('welcome', on_welcome_command, filters.ChatType.PRIVATE))
    bot.add_handler(CommandHandler('placeholders', on_placeholders_command, filters.ChatType.PRIVATE))

    # private chat: mixed
    bot.add_handler(PrefixHandler(COMMAND_PREFIXES, 'help', on_help_command, filters.ChatType.PRIVATE))

    # private chat: users
    bot.add_handler(CommandHandler('start', on_start_command, filters.ChatType.PRIVATE))
    bot.add_handler(CommandHandler('lang', on_lang_command, filters.ChatType.PRIVATE))
    bot.add_handler(MessageHandler(filters.ChatType.PRIVATE, on_user_message))

    # staff chat
    bot.add_handler(PrefixHandler(COMMAND_PREFIXES, 'setstaff', on_setstaff_command, filters.ChatType.GROUPS))
    bot.add_handler(PrefixHandler(COMMAND_PREFIXES, 'reloadadmins', on_reloadadmins_command, filters.ChatType.GROUPS))
    bot.add_handler(PrefixHandler(COMMAND_PREFIXES, ['ban', 'shadowban'], on_ban_command, filters.ChatType.GROUPS & filter_reply_to_bot))
    bot.add_handler(PrefixHandler(COMMAND_PREFIXES, 'unban', on_unban_command, filters.ChatType.GROUPS & filter_reply_to_bot))
    bot.add_handler(PrefixHandler(COMMAND_PREFIXES, 'info', on_info_command, filters.ChatType.GROUPS & filter_reply_to_bot))
    bot.add_handler(MessageHandler(filters.ChatType.GROUPS & filter_reply_to_bot, on_bot_message_reply))
    # bot.add_handler(CommandHandler('chatid', on_chatid_command, filters.ChatType.GROUPS))

    # callback query
    bot.add_handler(CallbackQueryHandler(on_set_language_button, pattern="^setlang:(..)$"))
    bot.add_handler(CallbackQueryHandler(on_setwelcome_language_button, pattern="^setwelcome:(..)$"))
    bot.add_handler(CallbackQueryHandler(on_getwelcome_language_button, pattern="^getwelcome:(..)$"))
    bot.add_handler(CallbackQueryHandler(on_unsetwelcome_language_button, pattern="^unsetwelcome:(..)$"))

    # other
    bot.add_handler(MessageHandler(new_group, on_new_group_chat))
    bot.add_handler(ChatMemberHandler(on_chat_member_update, ChatMemberHandler.ANY_CHAT_MEMBER))

    logger.info("polling for updates...")
    bot.run_polling(
        drop_pending_updates=False,
        allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY, Update.CHAT_MEMBER, Update.MY_CHAT_MEMBER]
    )


if __name__ == '__main__':
    main()
