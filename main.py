import logging
from typing import Optional, Tuple

import pytz
from sqlalchemy.orm import Session
from sqlalchemy import update as sqlalchemy_update
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberAdministrator, User as TelegramUser
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, Defaults, filters, MessageHandler, \
    CallbackQueryHandler
from telegram.ext.filters import MessageFilter

from database.models import User, UserMessage, Chat, Setting
import decorators
import utilities
from emojis import Emoji
from config import config

logger = logging.getLogger(__name__)

defaults = Defaults(
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        tzinfo=pytz.timezone('Europe/Rome')
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
    if user_language != "it":
        button = InlineKeyboardButton("it", callback_data="setlang:it")
        keyboard[0].append(button)
    if user_language != "fr":
        button = InlineKeyboardButton("fr", callback_data="setlang:fr")
        keyboard[0].append(button)
    if user_language != "es":
        button = InlineKeyboardButton("es", callback_data="setlang:es")
        keyboard[0].append(button)
    if user_language != "en":
        button = InlineKeyboardButton("en", callback_data="setlang:en")
        keyboard[0].append(button)

    return InlineKeyboardMarkup(keyboard)


@decorators.pass_session(pass_user=True)
async def on_set_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"user changed language: %s", update.callback_query.data)
    selected_language = context.matches[0].group(1)
    user.selected_language = selected_language

    await update.callback_query.answer(f"langauge set to {user.selected_language}", show_alert=False)

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)
    reply_markup = get_start_reply_markup(language_code)
    await update.effective_message.edit_text(f"language set: {language_code}", reply_markup=reply_markup)

    user.set_started(update_last_message=True)


@decorators.pass_session(pass_user=True)
async def on_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"/start from {update.effective_user.id} ({update.effective_user.first_name}) (lang: {update.effective_user.language_code})")

    language_code = get_language_code(user.selected_language, update.effective_user.language_code)

    setting_key = f"welcome_{language_code}"
    # TODO: query per estrarre id di chat con default == True
    welcome_setting = get_setting(session, setting_key, -1001072024039, create_if_missing=False)
    if not welcome_setting:
        logger.warning(f"no welcome setting for language {language_code}")
        return

    reply_markup = get_start_reply_markup(language_code)

    await update.message.reply_text(welcome_setting.value, reply_markup=reply_markup)

    user.set_started(update_last_message=True)


@decorators.pass_session(pass_user=True)
async def on_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info("new user message")

    user.update_metadata(update.effective_user)

    if user.banned:
        reason = user.banned_reason or "-"
        await update.message.reply_text(f"{Emoji.BANNED} You were banned from using this bot. Reason: {utilities.escape_html(reason)}")
        return

    chat: Chat = session.query(Chat).filter(Chat.default == True).one_or_none()
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


async def on_welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/welcome command from {update.effective_user.id} ({update.effective_user.full_name})")

    context.user_data["welcome_text"] = update.effective_message.text_html.lstrip("/welcome ")

    keyboard = [[
        InlineKeyboardButton("en", callback_data="setwelcome:en"),
        InlineKeyboardButton("it", callback_data="setwelcome:it"),
        InlineKeyboardButton("fr", callback_data="setwelcome:fr"),
        InlineKeyboardButton("es", callback_data="setwelcome:es"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(f"Select the language for this welcome text", reply_markup=reply_markup)


def get_setting(session: Session, key: str, chat_id: int, create_if_missing=True):
    setting: Setting = session.query(Setting).filter(
        Setting.chat_id == chat_id,
        Setting.key == key
    ).one_or_none()

    if not setting and create_if_missing:
        setting = Setting(chat_id=chat_id, key=key)
        session.add(setting)

    return setting


@decorators.pass_session(pass_user=True)
async def on_welcome_language_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None, user: Optional[User] = None):
    logger.info(f"setting welcome for language: %s", update.callback_query.data)
    selected_language = context.matches[0].group(1)

    chat: Chat = session.query(Chat).filter(Chat.default == True).one_or_none()
    if not chat:
        logger.warning("there is no staff chat set as default")
        await update.effective_message.edit_text("There's no staff chat set. Add me to the chat and use "
                                                 "<code>/setstaff</code> to set that chat as default staff chat")
        return

    setting_key = f"welcome_{selected_language}"
    setting = get_setting(session, setting_key, chat.chat_id)

    welcome_text = context.user_data.get("welcome_text")
    setting.value = welcome_text
    setting.updated_by = update.effective_user.id

    await update.effective_message.edit_text(f"Welcome text set ({selected_language}):\n\n{setting.value}")

    user.set_started(update_last_message=True)


@decorators.pass_session()
async def on_bot_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"reply to a bot message in {update.effective_chat.title} ({update.effective_chat.id})")

    chat_id = update.effective_chat.id
    replied_to_message_id = update.message.reply_to_message.message_id

    user_message: UserMessage = session.query(UserMessage).filter(
        UserMessage.forwarded_chat_id == chat_id,
        UserMessage.forwarded_message_id == replied_to_message_id
    ).one_or_none()

    if not user_message:
        logger.warning(f"couldn't find replied-to message, chat_id: {chat_id}; message_id: {replied_to_message_id}")
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

    # administrators: [ChatMemberAdministrator] = await update.effective_chat.get_administrators()
    # chat_queries.update_administrators(session, chat, administrators)


def main():
    utilities.load_logging_config('logging.json')

    # settings
    bot.add_handler(CommandHandler('welcome', on_welcome_command, filters.ChatType.PRIVATE))

    bot.add_handler(CommandHandler('start', on_start_command, filters.ChatType.PRIVATE))
    bot.add_handler(MessageHandler(filters.ChatType.PRIVATE, on_user_message))
    bot.add_handler(CommandHandler('chatid', on_chatid_command, filters.ChatType.GROUPS))
    bot.add_handler(MessageHandler(filters.ChatType.GROUPS & filter_reply_to_bot, on_bot_message_reply))

    # staff chat
    bot.add_handler(CommandHandler('setstaff', on_setstaff_command, filters.ChatType.GROUPS))

    # callback query
    bot.add_handler(CallbackQueryHandler(on_set_language_button, pattern="^setlang:(..)$"))
    bot.add_handler(CallbackQueryHandler(on_welcome_language_button, pattern="^setwelcome:(..)$"))

    # other
    bot.add_handler(MessageHandler(new_group, on_new_group_chat))

    logger.info("polling for updates...")
    bot.run_polling(
        drop_pending_updates=False,
        allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY, Update.CHAT_MEMBER, Update.MY_CHAT_MEMBER]
    )


if __name__ == '__main__':
    main()
