import logging
import random
from typing import Union, Iterable

import pytz
from sqlalchemy import update, null
from sqlalchemy.orm import Session
from telegram import Update, BotCommandScopeChat, ChatMemberOwner, ChatInviteLink, BotCommandScopeDefault
from telegram import BotCommand, BotCommandScopeAllPrivateChats
from telegram import ChatMember, ChatMemberAdministrator
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ApplicationBuilder, Application, ContextTypes, PicklePersistence, PersistenceInput
from telegram.ext import Defaults
from telegram.ext import ExtBot

from loader import load_modules
from database.base import get_session, Base, engine, session_scope
from database.models import ChatMember as DbChatMember, Chat
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

Base.metadata.create_all(engine)


async def set_bbr_commands(session: Session, bot: ExtBot):
    # first: reset all commands
    await bot.set_my_commands([], scope=BotCommandScopeDefault())

    default_english_commands = [
        BotCommand("start", "see the welcome message"),
        BotCommand("lang", "set your language")
    ]

    logger.info("setting bbr commands...")
    await bot.set_my_commands(
        default_english_commands,
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

    admin_commands = default_english_commands + [
        BotCommand("settings", "change the bot's global settings"),
        BotCommand("texts", "manage text messages that depend on the user's language"),
        BotCommand("placeholders", "list all available placeholders")
    ]
    staff_chat_administrators = chats.get_staff_chat_administrators(session)
    chat_member: DbChatMember
    for chat_member in staff_chat_administrators:
        logger.info(f"setting admin commands for {chat_member.user.user_id}...")
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_member.user_id))


async def set_flytek_commands(session: Session, bot: ExtBot):
    logger.info("setting flytek commands...")

    users_commands_private = [
        BotCommand("start", "chiedi 👀"),
        BotCommand("radar23", "feste")
    ]
    staff_commands_private = [
        BotCommand("radar23", "elenco feste"),
        BotCommand("radar24", "radar23, ma inoltrabile/copiabile"),
        BotCommand("ie", "feste senza data"),
        BotCommand("settings", "impostazioni bot"),
        BotCommand("texts", "testi risposte bot"),
    ]
    staff_chat_commands = [
        BotCommand("info", "id/in risposta: info su un utente"),
        BotCommand("ban", "in risposta: banna l'utente dall'utilizzo del bot"),
        BotCommand("shadowban", "in risposta: banna l'utente dall'utilizzo del bot"),
        BotCommand("unban", "in risposta: permetti all'utente di utilizzare il bot"),
        BotCommand("revoke", "revoca un messaggio inviato all'utente"),
        BotCommand("userschat", "id/in risposta: elenco delle chat di cui un utente fa parte"),
    ]
    evaluation_chat_commands = staff_chat_commands + [
        BotCommand("reset", "resetta richiesta utente"),
        BotCommand("accetta", "in risposta: accetta una richiesta utente"),
        BotCommand("rifiuta", "in risposta: rifiuta una richiesta utente"),
    ]

    await bot.set_my_commands(
        users_commands_private,
        scope=BotCommandScopeAllPrivateChats()
    )

    staff_chat = chats.get_chat(session, Chat.is_staff_chat)
    if staff_chat:
        await bot.set_my_commands(staff_chat_commands, scope=BotCommandScopeChat(staff_chat.chat_id))

        staff_chat_members = chat_members.get_chat_members(session, staff_chat.chat_id)
        chat_member: DbChatMember
        for chat_member in staff_chat_members:
            await bot.set_my_commands(staff_commands_private, scope=BotCommandScopeChat(chat_member.user_id))

    evaluation_chat = chats.get_chat(session, Chat.is_evaluation_chat)
    if evaluation_chat:
        await bot.set_my_commands(evaluation_chat_commands, scope=BotCommandScopeChat(evaluation_chat.chat_id))


async def post_init(application: Application) -> None:
    bot: ExtBot = application.bot

    session: Session = get_session()

    logger.info("populating default settings...")
    for bot_setting_key, bot_setting_data in BOT_SETTINGS_DEFAULTS.items():
        setting = session.query(BotSetting).filter(BotSetting.key == bot_setting_key).one_or_none()
        if not setting:
            setting = BotSetting(
                bot_setting_key, bot_setting_data["default"],
                telegram_media=bot_setting_data["telegram_media"],
                show_if_true_key=bot_setting_data["show_if_true_key"]
            )
            session.add(setting)

    session.commit()

    staff_chat = chats.get_chat(session, Chat.is_staff_chat)
    users_chat = chats.get_chat(session, Chat.is_users_chat)
    evaluation_chat = chats.get_chat(session, Chat.is_evaluation_chat)
    for chat in [staff_chat, users_chat, evaluation_chat]:
        if not chat:
            logger.info("chat is none, next chat...")
            continue

        try:
            staff_chat_chat_member: ChatMember = await bot.get_chat_member(chat.chat_id, bot.id)
        except BadRequest as e:
            logger.error(f"error while gettign {chat.title}'s ChatMember: {e}")
            if "chat not found" in e.message.lower():
                logger.warning(f"{chat.title} {chat.chat_id} not found: resetting that type of chat...")
                if chat.is_staff_chat:
                    chats.reset_staff_chat(session)
                elif chat.is_users_chat:
                    chats.reset_users_chat(session)
                elif chat.is_evaluation_chat:
                    chats.reset_events_chat(session)

            session.commit()
            continue

        if not isinstance(staff_chat_chat_member, ChatMemberAdministrator):
            logger.info(f"not an admin in {chat.title} {chat.chat_id}, current status: {staff_chat_chat_member.status}")
            chat.unset_as_administrator()
        else:
            logger.info(f"admin in {chat.title} {chat.chat_id}, can_delete_messages: {staff_chat_chat_member.can_delete_messages}")
            chat.set_as_administrator(
                can_delete_messages=staff_chat_chat_member.can_delete_messages,
                can_invite_users=staff_chat_chat_member.can_invite_users
            )

        session.add(chat)
        session.commit()

        logger.info(f"updating {chat.title} administrators...")
        # noinspection PyTypeChecker
        administrators: Iterable[Union[ChatMemberAdministrator, ChatMemberOwner]] = await bot.get_chat_administrators(chat.chat_id)
        chat_members.save_administrators(session, chat.chat_id, administrators)
        session.commit()

    if config.handlers.mode == "bbr":
        await set_bbr_commands(session, bot)
    else:
        await set_flytek_commands(session, bot)


async def change_my_name(context: ContextTypes.DEFAULT_TYPE):
    if not utilities.is_test_bot():
        return

    name = f"[TEST] bbr bot {utilities.now_str()}"
    logger.debug(f"changing name to \"{name}\"")
    try:
        await context.bot.set_my_name(name=name)
    except (TelegramError, BadRequest) as e:
        logger.debug(f"error while changing name: {e.message}")


async def generate_one_time_link(context: ContextTypes.DEFAULT_TYPE):
    if not utilities.is_test_bot():
        return

    if "errors_count" in context.bot_data and context.bot_data["errors_count"] >= 10:
        logger.debug("too many errors")
        return

    logger.debug(f"running at {utilities.now_str()}")
    with session_scope() as session:
        now_str = utilities.now_str()
        users_chat = chats.get_chat(session, Chat.is_users_chat)
        for i in range(5):
            try:
                chat_invite_link: ChatInviteLink = await context.bot.create_chat_invite_link(
                    users_chat.chat_id,
                    member_limit=1,
                    name=f"#{i+1} {now_str}"
                )
                invite_link = chat_invite_link.invite_link
                logger.debug(f"generated link {now_str}: {invite_link}")
            except (TelegramError, BadRequest) as e:
                logger.error(f"error while generating invite link for chat {users_chat.chat_id}: {e}")
                await context.bot.send_message(users_chat.chat_id, f"invite link error #{i+1}: {e}")

                if "errors_count" not in context.bot_data:
                    context.bot_data["errors_count"] = 0
                context.bot_data["errors_count"] += 1


def main():
    utilities.load_logging_config('logging.json')

    persistence = PicklePersistence(
        filepath='data.pickle',
        store_data=PersistenceInput(chat_data=False, user_data=False, bot_data=False)
    )

    app: Application = ApplicationBuilder() \
        .token(config.telegram.token) \
        .defaults(defaults) \
        .persistence(persistence) \
        .post_init(post_init) \
        .build()

    load_modules(app, "plugins", manifest_file_name=config.handlers.manifest)

    # app.job_queue.run_repeating(change_my_name, interval=60*10, first=10)
    # app.job_queue.run_repeating(generate_one_time_link, interval=10*60, first=10)

    logger.info(f"polling for updates...")
    app.run_polling(
        drop_pending_updates=False,
        allowed_updates=[
            Update.MESSAGE,
            Update.CHANNEL_POST,
            Update.EDITED_MESSAGE,
            Update.EDITED_CHANNEL_POST,
            Update.CALLBACK_QUERY,
            Update.CHAT_MEMBER,
            Update.MY_CHAT_MEMBER
        ]
    )


if __name__ == '__main__':
    main()
