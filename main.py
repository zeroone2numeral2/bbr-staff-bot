import logging
from typing import Union, Iterable

import pytz
from sqlalchemy.orm import Session
from telegram import Update, BotCommandScopeChat, ChatMemberOwner
from telegram import BotCommand, BotCommandScopeAllPrivateChats
from telegram import ChatMember, ChatMemberAdministrator
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, Application
from telegram.ext import Defaults
from telegram.ext import ExtBot

from loader import load_modules
from database.base import get_session
from database.models import ChatMember as DbChatMember
from database.models import BotSetting
from database.queries import chats, chat_members
import utilities
from constants import Language, BOT_SETTINGS_DEFAULTS
from config import config

logger = logging.getLogger(__name__)

defaults = Defaults(
    parse_mode=ParseMode.HTML,
    disable_web_page_preview=True,
    tzinfo=pytz.timezone('Europe/Rome'),
    quote=False
)


async def post_init(application: Application) -> None:
    bot: ExtBot = application.bot

    defaul_english_commands = [
        BotCommand("start", "see the welcome message"),
        BotCommand("lang", "set your language")
    ]

    await bot.set_my_commands(
        defaul_english_commands,
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
        logger.info("no staff chat set")
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

    logger.info("updating staff chat administrators...")
    # noinspection PyTypeChecker
    administrators: Iterable[Union[ChatMemberAdministrator, ChatMemberOwner]] = await bot.get_chat_administrators(staff_chat.chat_id)
    chat_members.save_administrators(session, staff_chat.chat_id, administrators)
    session.commit()

    admin_commands = defaul_english_commands + [
        BotCommand("settings", "change the bot's global settings"),
        BotCommand("texts", "manage text messages that depend on the user's language"),
        BotCommand("placeholders", "list all available placeholders")
    ]
    staff_chat_administrators = chats.get_staff_chat_administrators(session)
    chat_member: DbChatMember
    for chat_member in staff_chat_administrators:
        logger.info(f"setting admin commands for {chat_member.user.user_id}...")
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_member.user_id))


def main():
    utilities.load_logging_config('logging.json')

    app: Application = ApplicationBuilder() \
        .token(config.telegram.token) \
        .defaults(defaults) \
        .post_init(post_init) \
        .build()

    load_modules(app, "plugins", manifest_file_name=config.handlers.manifest)

    # edited messages NEED to be catched before anything else, otherwise they will be processed by other MessageHandlers
    # MOVED TO staff.chat.edits and users.edits

    # private chat (admins)
    # MOVED TO staff.private.settings_manual

    # private chat (admins): bot settings
    # MOVED TO staff.private.settings

    # private chat (admins): localized texts
    # MOVED TO staff.private.ltexts

    # private chat: admins + users
    # MOVED TO help

    # private chat: users
    # MOVED TO users.start
    # MOVED TO users.lang
    # MOVED TO users.revoke
    # MOVED TO users.message

    # staff chat
    # MOVED TO staff.chat.setstaff
    # MOVED TO staff.chat.reloadadmins
    # MOVED TO staff.chat.ban
    # MOVED TO staff.chat.info
    # MOVED TO staff.chat.revoke
    # MOVED TO staff.chat.reply

    # callback query
    # MOVED TO users.lang
    # MOVED TO users.start

    # chat_member updates
    # MOVED TO chat_members.newchat
    # MOVED TO chat_members.update

    logger.info(f"polling for updates...")
    app.run_polling(
        drop_pending_updates=False,
        allowed_updates=[Update.MESSAGE, Update.EDITED_MESSAGE, Update.CALLBACK_QUERY, Update.CHAT_MEMBER, Update.MY_CHAT_MEMBER]
    )


if __name__ == '__main__':
    main()
