import logging
from typing import Union, Iterable

import pytz
from sqlalchemy.orm import Session
from telegram import BotCommand, BotCommandScopeAllPrivateChats
from telegram import ChatMember, ChatMemberAdministrator
from telegram import Update, BotCommandScopeChat, ChatMemberOwner, BotCommandScopeDefault
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, Application, PicklePersistence, PersistenceInput
from telegram.ext import Defaults
from telegram.ext import ExtBot

import utilities
from config import config
from constants import Language, BOT_SETTINGS_DEFAULTS
from database.base import get_session, Base, engine
from database.models import BotSetting
from database.models import ChatMember as DbChatMember, Chat, Event
from database.queries import chats, chat_members, events
from loader import load_modules
from plugins.events.job import parties_message_job

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
    staff_chat_member = chat_members.get_chat_chat_members(session, Chat.is_staff_chat)
    chat_member: DbChatMember
    for chat_member in staff_chat_member:
        logger.info(f"setting admin commands for {chat_member.user.user_id}...")
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_member.user_id))
        except BadRequest as e:
            # maybe the suer never started the bot
            logger.warning(f"...failed: {e}")


async def set_flytek_commands(session: Session, bot: ExtBot):
    # first: reset all commands
    await bot.set_my_commands([], scope=BotCommandScopeDefault())

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

        staff_chat_members = chat_members.get_chat_chat_members(session, Chat.is_staff_chat)
        chat_member: DbChatMember
        for chat_member in staff_chat_members:
            try:
                await bot.set_my_commands(staff_commands_private, scope=BotCommandScopeChat(chat_member.user_id))
            except BadRequest as e:
                # maybe the suer never started the bot
                logger.warning(f"...failed: {e}")

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

    logger.info("fixing events dates...")
    all_events = events.get_all_events(session)
    event: Event
    for event in all_events:
        event.populate_date_fields()
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
            logger.error(f"error while getting {chat.title}'s ChatMember: {e}")
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

    session.commit()
    session.close()


def main():
    utilities.load_logging_config('logging.json')

    # persistence was initially added to make conversation statuses persistent,
    # but we might use it also for temporary data in user_data and bot_data
    persistence = PicklePersistence(
        filepath='temp_data_persistence.pickle',
        store_data=PersistenceInput(chat_data=False, user_data=True, bot_data=True)
    )

    app: Application = ApplicationBuilder() \
        .token(config.telegram.token) \
        .defaults(defaults) \
        .persistence(persistence) \
        .post_init(post_init) \
        .build()

    load_modules(app, "plugins", manifest_file_name=config.handlers.manifest)

    app.job_queue.run_repeating(parties_message_job, interval=config.settings.parties_message_job_frequency * 60, first=20)

    logger.info(f"polling for updates...")
    app.run_polling(
        drop_pending_updates=utilities.is_test_bot(),
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
