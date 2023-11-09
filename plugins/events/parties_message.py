import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import decorators
import utilities
from constants import Group, TempDataKey, BotSettingKey, WEEKDAYS_IT, BotSettingCategory
from database.models import Chat, PartiesMessage
from database.queries import chats, parties_messages, settings
from ext.filters import ChatFilter, Filter
from plugins.events.common import EventFilter
from plugins.events.job import parties_message_job, LIST_TYPE_DESCRIPTION, get_events_text, PARTIES_MESSAGE_TYPES_ARGS
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_updatelists_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/updatelists {utilities.log(update)}")

    events_chat = chats.get_chat(session, Chat.is_events_chat)

    context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True

    message_links = []
    for events_type, _ in LIST_TYPE_DESCRIPTION.items():
        parties_message: Optional[PartiesMessage] = parties_messages.get_last_parties_message(session, events_chat.chat_id, events_type)
        if parties_message:
            message_links.append(parties_message.message_link())

    await update.message.reply_html(f"Provo ad aggiornare questi messaggi:\n{', '.join(message_links)}")

    context.job_queue.run_once(parties_message_job, when=1)


@decorators.catch_exception()
@decorators.pass_session()
async def on_sendlists_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/sendlists {utilities.log(update)}")

    events_chat = chats.get_chat(session, Chat.is_events_chat)

    context.bot_data[TempDataKey.FORCE_POST_PARTIES_MESSAGE] = True

    await update.message.reply_html(f"Invio delle nuove liste in {utilities.escape_html(events_chat.title)}...")

    context.job_queue.run_once(parties_message_job, when=1)


@decorators.catch_exception()
@decorators.pass_session()
async def on_getlists_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/getlists {utilities.log(update)}")

    discussion_group_messages_links = settings.get_or_create(session, BotSettingKey.PARTIES_LIST_DISCUSSION_LINK).value()
    weeks = settings.get_or_create(session, BotSettingKey.PARTIES_LIST_WEEKS).value()

    now = utilities.now(tz=True)
    for filter_key, args in PARTIES_MESSAGE_TYPES_ARGS.items():
        args.append(EventFilter.WEEK) if weeks <= 1 else args.append(EventFilter.WEEK_2)
        text = get_events_text(
            session=session,
            filter_key=filter_key,
            now=now,
            args=args,
            discussion_group_messages_links=discussion_group_messages_links
        )
        if not text:
            text = f"nessuna festa per <code>{filter_key}</code>"

        await update.message.reply_html(f"{text}")


@decorators.catch_exception()
@decorators.pass_session()
async def on_listsinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/listsinfo {utilities.log(update)}")

    pl_settings = settings.get_settings_as_dict(session, include_categories=BotSettingCategory.PARTIES_LIST)
    enabled = pl_settings[BotSettingKey.PARTIES_LIST].value()
    weeks = pl_settings[BotSettingKey.PARTIES_LIST_WEEKS].value()
    weekday = pl_settings[BotSettingKey.PARTIES_LIST_WEEKDAY].value()
    hour = pl_settings[BotSettingKey.PARTIES_LIST_HOUR].value()
    pin = pl_settings[BotSettingKey.PARTIES_LIST_PIN].value()
    group_messages_links = pl_settings[BotSettingKey.PARTIES_LIST_DISCUSSION_LINK].value()

    list_was_updated = context.bot_data.get(TempDataKey.UPDATE_PARTIES_MESSAGE, False)  # do not pop

    now = utilities.now()
    await update.message.reply_html(
        f"<b>Abilitato</b>: {utilities.bool_to_str_it(enabled, si_no=True)} ({weeks} settimana/e)\n"
        f"<b>Lista da aggiornare</b>: {utilities.bool_to_str_it(list_was_updated, si_no=True)}\n"
        f"<b>Giorno</b>: {WEEKDAYS_IT[weekday]}\n"
        f"<b>Ora</b>: {hour} (ora attuale: {now.hour}:{now.minute})\n"
        f"<b>Fissa messaggi</b>: {utilities.bool_to_str_it(pin, si_no=True)}\n"
        f"<b>Linka messaggi canale nel gruppo di discussione</b>: {utilities.bool_to_str_it(group_messages_links, si_no=True)}\n"
        f"<b>Frequenza aggiornamento</b>: {config.settings.parties_message_job_frequency} minuti"
    )


HANDLERS = (
    (CommandHandler(["updatelists", "ul"], on_updatelists_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["sendlists", "sl"], on_sendlists_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["getlists", "gl"], on_getlists_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["listsinfo"], on_listsinfo_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
