import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import decorators
import utilities
from config import config
from constants import Group, TempDataKey, BotSettingKey, WEEKDAYS_IT, BotSettingCategory
from database.models import Chat, PartiesMessage
from database.queries import chats, parties_messages, settings
from ext.filters import ChatFilter, Filter
from plugins.events.common import EventFilter, EventFormatting
from plugins.events.job import parties_message_job, LIST_TYPE_DESCRIPTION, get_events_text, PARTIES_MESSAGE_TYPES_ARGS

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_partiesjob_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/partiesjob {utilities.log(update)}")

    send_to_group = settings.get_or_create(session, BotSettingKey.PARTIES_LIST_POST_TO_USERS_CHAT).value()
    if send_to_group:
        target_chat = chats.get_chat(session, Chat.is_users_chat)
    else:
        target_chat = chats.get_chat(session, Chat.is_events_chat)

    list_needs_update = context.bot_data.get(TempDataKey.UPDATE_PARTIES_MESSAGE, False)
    text = (f"Verrà eseguito il job che controlla se aggiornare i messaggi con la lista delle feste in {target_chat.title} "
            f"ogni {config.settings.parties_message_job_frequency} minuti (feste aggiunte/modificate dall'ultima esecuzione? "
            f"{utilities.bool_to_str_it(list_needs_update, si_no=True)})")

    message_descriptions = []
    for events_type, _ in LIST_TYPE_DESCRIPTION.items():
        parties_message: Optional[PartiesMessage] = parties_messages.get_last_parties_message(session, target_chat.chat_id, events_type)
        if parties_message:
            description = f"{parties_message.message_link(parties_message.events_type)}"
            message_descriptions.append(description)

    if message_descriptions:
        text += f"\n\nUltimi messaggi inviati: {', '.join(message_descriptions)}"
    else:
        text += f"\n\nUltimi messaggi inviati: nessuno (se il giorno e l'ora sono giusti, verranno postati dei nuovi messaggi)"

    if context.args:
        if context.args[0].lower() == "forceupdate":
            logger.info("setting flag to force-update the list")
            context.bot_data[TempDataKey.FORCE_UPDATE_PARTIES_MESSAGE] = True
            text += "\n\nIl bot agirà come se siano state pubblicate/modificate feste nel canale"
        elif context.args[0].lower() == "forcepost":
            logger.info("setting flag to force-post the list")
            context.bot_data[TempDataKey.FORCE_POST_PARTIES_MESSAGE] = True
            text += "\n\nVerrà forzato l'invio di nuovi messaggi"

    await update.message.reply_html(text)

    context.job_queue.run_once(parties_message_job, when=1)


@decorators.catch_exception()
@decorators.pass_session()
async def on_getlists_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/getlists {utilities.log(update)}")

    discussion_group_messages_links = settings.get_or_create(session, BotSettingKey.PARTIES_LIST_DISCUSSION_LINK).value()
    weeks = settings.get_or_create(session, BotSettingKey.PARTIES_LIST_WEEKS).value()
    send_to_group = settings.get_or_create(session, BotSettingKey.PARTIES_LIST_POST_TO_USERS_CHAT).value()

    last_filter_key = list(PARTIES_MESSAGE_TYPES_ARGS.keys())[-1]

    now = utilities.now(tz=True, dst_check=True)
    for filter_key, args in PARTIES_MESSAGE_TYPES_ARGS.items():
        args.append(EventFilter.WEEK) if weeks <= 1 else args.append(EventFilter.WEEK_2)
        text = get_events_text(
            session=session,
            filter_key=filter_key,
            now=now,
            args=args,
            bot_username=context.bot.username,
            send_to_group=send_to_group,
            append_bottom_text=filter_key == last_filter_key,
            formatting=EventFormatting(discussion_group_link=discussion_group_messages_links)
        )
        if not text:
            text = f"nessuna festa per <code>{filter_key}</code>"

        await update.message.reply_html(f"{text}")


@decorators.catch_exception()
@decorators.pass_session()
async def on_dellist_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/dellists {utilities.log(update)}")

    if not context.args:
        return

    message_link = context.args[0]
    chat_id, message_id = utilities.unpack_message_link(message_link)
    if not chat_id:
        await update.message.reply_text("Il link utilizzato non è valido")
        return

    ids_str = f"<code>{chat_id}</code>/<code>{message_id}</code>"

    parties_message: Optional[PartiesMessage] = parties_messages.get_parties_message(session, chat_id, message_id)
    if not parties_message:
        logger.info(f"no PartiesMessage was found for message {message_id} in chat {chat_id}")
        await update.effective_message.reply_text(f"Nessuna festa salvata per <a href=\"{message_link}\">questo messaggio</a> ({ids_str})")
        return

    parties_message.deleted = True
    await update.effective_message.reply_text(
        f"<a href=\"{message_link}\">Messaggio</a> ({ids_str}, tipo: <code>{parties_message.events_type}</code>) "
        f"contrassegnato come eliminato, non verrà più considerato come valido per aggiornare le feste"
    )


@decorators.catch_exception()
@decorators.pass_session()
async def on_listsinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/listsinfo {utilities.log(update)}")

    # pls: Parties List Settings
    pls_dict = settings.get_settings_as_dict(session, include_categories=BotSettingCategory.PARTIES_LIST)
    enabled = pls_dict[BotSettingKey.PARTIES_LIST].value()
    post_to_group = pls_dict[BotSettingKey.PARTIES_LIST_POST_TO_USERS_CHAT].value()
    update_only = pls_dict[BotSettingKey.PARTIES_LIST_UPDATE_ONLY].value()
    weeks = pls_dict[BotSettingKey.PARTIES_LIST_WEEKS].value()
    weekday = pls_dict[BotSettingKey.PARTIES_LIST_WEEKDAY].value()
    hour = pls_dict[BotSettingKey.PARTIES_LIST_HOUR].value()
    pin = pls_dict[BotSettingKey.PARTIES_LIST_PIN].value()
    delete_old = pls_dict[BotSettingKey.PARTIES_LIST_DELETE_OLD].value()
    group_messages_links = pls_dict[BotSettingKey.PARTIES_LIST_DISCUSSION_LINK].value()

    list_was_updated = context.bot_data.get(TempDataKey.UPDATE_PARTIES_MESSAGE, False)  # do not pop

    now_it = utilities.now(tz=True, dst_check=True)
    now_it_hour = utilities.format_datetime(now_it, format_str="%H:%M")
    await update.message.reply_html(
        f"<b>Abilitato</b>: {utilities.bool_to_str_it(enabled, si_no=True)} ({weeks} settimana/e)\n"
        f"<b>Posta nel gruppo invece che nel canale</b>: {utilities.bool_to_str_it(post_to_group, si_no=True)}\n"
        f"<b>Lista da aggiornare</b>: {utilities.bool_to_str_it(list_was_updated, si_no=True)}\n"
        f"<b>Invia lista settimanalmente (invece che aggiornare mex esistente)</b>: {utilities.bool_to_str_it(not update_only, si_no=True)}\n"
        f"<b>Giorno</b>: {WEEKDAYS_IT[weekday]}, alle {hour} (ora attuale: {now_it_hour})\n"
        f"<b>Fissa messaggi</b>: {utilities.bool_to_str_it(pin, si_no=True)}\n"
        f"<b>Elimina vecchio messaggio dopo averne inviato uno nuovo</b>: {utilities.bool_to_str_it(delete_old, si_no=True)}\n"
        f"<b>Linka messaggi canale nel gruppo di discussione</b>: {utilities.bool_to_str_it(group_messages_links, si_no=True)}\n"
        f"<b>Frequenza aggiornamento</b>: {config.settings.parties_message_job_frequency} minuti"
    )


HANDLERS = (
    (CommandHandler(["partiesjob", "pj"], on_partiesjob_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["getlists", "gl"], on_getlists_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["listsinfo"], on_listsinfo_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["dellist"], on_dellist_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
