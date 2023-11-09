import json
import logging
import traceback
from typing import Union, Iterable, Optional

import pytz
from sqlalchemy import select
from sqlalchemy.orm import Session
from telegram import BotCommand, BotCommandScopeAllPrivateChats
from telegram import ChatMemberAdministrator
from telegram import Update, BotCommandScopeChat, ChatMemberOwner, BotCommandScopeDefault
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError
from telegram.ext import ApplicationBuilder, Application, PicklePersistence, PersistenceInput, ContextTypes, \
    CommandHandler
from telegram.ext import Defaults
from telegram.ext import ExtBot

import utilities
from config import config
from constants import Language, HandlersMode, BOT_SETTINGS_DEFAULTS
from database.base import get_session, Base, engine
from database.models import BotSetting, ChatMember
from database.models import ChatMember as DbChatMember, Chat, Event
from database.queries import chats, chat_members, events
from loader import load_modules
from plugins.events.job import parties_message_job

logger = logging.getLogger(__name__)
logger_startup = logging.getLogger("startup")

Base.metadata.create_all(engine)

defaults = Defaults(
    parse_mode=ParseMode.HTML,
    disable_web_page_preview=True,
    # tzinfo=pytz.utc,  # pytz.utc is the default
    quote=False
)

# persistence was initially added to make conversation statuses persistent,
# but we might use it also for temporary data in user_data and bot_data
persistence = PicklePersistence(
    filepath='temp_data_persistence.pickle',
    store_data=PersistenceInput(chat_data=False, user_data=True, bot_data=True)
)

builder = ApplicationBuilder()
builder.token(config.telegram.token)
builder.defaults(defaults)
builder.persistence(persistence)


async def set_bbr_commands(session: Session, bot: ExtBot):
    # first: reset all commands
    await bot.set_my_commands([], scope=BotCommandScopeDefault())

    default_english_commands = [
        BotCommand("start", "see the welcome message"),
        BotCommand("lang", "set your language")
    ]

    logger_startup.info("setting bbr commands...")
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
        logger_startup.info(f"setting admin commands for {chat_member.user.user_id}...")
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_member.user_id))
        except BadRequest as e:
            # maybe the suer never started the bot
            logger_startup.warning(f"...failed for {chat_member.user_id}: {e}")


async def set_flytek_commands(session: Session, bot: ExtBot):
    # first: reset all commands
    await bot.set_my_commands([], scope=BotCommandScopeDefault())

    logger_startup.info("setting flytek commands...")

    users_commands_private = [
        BotCommand("start", "chiedi 👀"),
        # BotCommand("radar23", "feste")
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
                logger_startup.warning(f"...failed for {chat_member.user_id}: {e}")

    evaluation_chat = chats.get_chat(session, Chat.is_evaluation_chat)
    if evaluation_chat:
        await bot.set_my_commands(evaluation_chat_commands, scope=BotCommandScopeChat(evaluation_chat.chat_id))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # https://docs.python-telegram-bot.org/en/v20.6/examples.errorhandlerbot.html
    if isinstance(context.error, NetworkError):
        logger.error(f"NetworkError: {context.error}")
        return

    logger.error("uncaught exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together
    # traceback_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    # traceback_string = "".join(traceback_list)

    # might need to add some logic to deal with messages longer than the 4096 character limit
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    logger.error(f"update that caused the exception: {update_str}")
    logger.error(f"context.chat_data: {context.chat_data}")
    logger.error(f"context.user_data: {context.user_data}")

    # text = (
    #     "An exception was raised while handling an update\n"
    #     f"<pre>update = {utilities.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
    #     "</pre>\n\n"
    #     f"<pre>context.chat_data = {utilities.escape(str(context.chat_data))}</pre>\n\n"
    #     f"<pre>context.user_data = {utilities.escape(str(context.user_data))}</pre>\n\n"
    #     f"<pre>{utilities.escape(traceback_string)}</pre>"
    # )
    text = f"#flytekbbr error: <code>{utilities.escape(str(context.error))}</code>"

    await context.bot.send_message(config.telegram.admins[0], text)


async def test_bad_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Raise an error to trigger the error handler."""
    await context.bot.wrong_method_name()  # type: ignore[attr-defined]


async def post_init(application: Application) -> None:
    bot: ExtBot = application.bot

    session: Session = get_session()

    logger_startup.info("populating default settings...")
    for bot_setting_key, bot_setting_data in BOT_SETTINGS_DEFAULTS.items():
        setting: Optional[BotSetting] = session.query(BotSetting).filter(BotSetting.key == bot_setting_key).one_or_none()
        if not setting:
            setting = BotSetting(
                key=bot_setting_key,
                category=bot_setting_data["category"],
                value=bot_setting_data["default"],
                telegram_media=bot_setting_data["telegram_media"],
                show_if_true_key=bot_setting_data["show_if_true_key"]
            )
            session.add(setting)
        elif not setting.category:
            setting.category = bot_setting_data["category"]

    session.commit()

    staff_chat = chats.get_chat(session, Chat.is_staff_chat)
    users_chat = chats.get_chat(session, Chat.is_users_chat)
    evaluation_chat = chats.get_chat(session, Chat.is_evaluation_chat)
    for chat in [staff_chat, users_chat, evaluation_chat]:
        if not chat:
            logger_startup.info("chat is none, next chat...")
            continue

        try:
            staff_chat_chat_member: ChatMember = await bot.get_chat_member(chat.chat_id, bot.id)
        except BadRequest as e:
            logger_startup.error(f"error while getting {chat.title}'s ChatMember: {e}")
            if "chat not found" in e.message.lower():
                logger_startup.warning(f"{chat.title} {chat.chat_id} not found: resetting that type of chat...")
                if chat.is_staff_chat:
                    chats.reset_staff_chat(session)
                elif chat.is_users_chat:
                    chats.reset_users_chat(session)
                elif chat.is_evaluation_chat:
                    chats.reset_events_chat(session)

            session.commit()
            continue

        if not isinstance(staff_chat_chat_member, ChatMemberAdministrator):
            logger_startup.info(f"not an admin in {chat.title} {chat.chat_id}, current status: {staff_chat_chat_member.status}")
            chat.unset_as_administrator()
        else:
            logger_startup.info(f"admin in {chat.title} {chat.chat_id}, can_delete_messages: {staff_chat_chat_member.can_delete_messages}")
            chat.set_as_administrator(
                can_delete_messages=staff_chat_chat_member.can_delete_messages,
                can_invite_users=staff_chat_chat_member.can_invite_users
            )

        session.add(chat)
        session.commit()

        logger_startup.info(f"updating {chat.title} administrators...")
        # noinspection PyTypeChecker
        administrators: Iterable[Union[ChatMemberAdministrator, ChatMemberOwner]] = await bot.get_chat_administrators(chat.chat_id)
        chat_members.save_administrators(session, chat.chat_id, administrators)
        session.commit()

    if config.handlers.mode == HandlersMode.BBR:
        await set_bbr_commands(session, bot)
    else:
        await set_flytek_commands(session, bot)

    session.commit()
    session.close()


builder.post_init(post_init)
app: Application = builder.build()
app.bot.initialize()
bot_info = app.bot


def main():
    utilities.load_logging_config('logging.json')

    load_modules(app, "plugins", manifest_file_name=config.handlers.manifest)

    if config.handlers.mode == HandlersMode.FLYTEK:
        app.job_queue.run_repeating(parties_message_job, interval=config.settings.parties_message_job_frequency * 60, first=20)

    # app.add_handler(CommandHandler("bad_command", test_bad_command))
    app.add_error_handler(error_handler)

    drop_pending_updates = utilities.is_test_bot()

    logger_startup.info(f"polling for updates (drop_pending_updates={drop_pending_updates})...")
    app.run_polling(
        drop_pending_updates=drop_pending_updates,
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
