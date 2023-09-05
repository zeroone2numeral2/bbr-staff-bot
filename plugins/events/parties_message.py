import datetime
import json
import logging
import re
from re import Match
from typing import Optional, Tuple, List, Union

import telegram.constants
from sqlalchemy import true, false, null
from sqlalchemy.orm import Session
from telegram import Update, Message, MessageEntity, InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser, Chat as TelegramChat
from telegram.ext import ContextTypes, filters, MessageHandler, CommandHandler, CallbackContext, CallbackQueryHandler
from telegram.constants import MessageLimit

from emojis import Emoji, Flag
from ext.filters import ChatFilter, Filter
from plugins.events.job import parties_message_job, FILTER_DESCRIPTION
from database.models import Chat, Event, EventTypeHashtag, EVENT_TYPE, User, BotSetting, EventType, PartiesMessage
from database.queries import settings, events, chats, chat_members, private_chat_messages, parties_messages
import decorators
import utilities
from constants import BotSettingKey, Group, Regex, REGIONS_DATA, RegionName, MediaType, MONTHS_IT, TempDataKey, Timeout
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_updatelists_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/updatelists {utilities.log(update)}")

    events_chat = chats.get_chat(session, Chat.is_events_chat)

    context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True

    message_links = []
    for events_type, _ in FILTER_DESCRIPTION.items():
        parties_message: Optional[PartiesMessage] = parties_messages.get_last_parties_message(session, events_chat.chat_id, events_type)
        if parties_message:
            message_links.append(parties_message.message_link())

    await update.message.reply_html(f"Provo ad aggiornare questi messaggi:\n{', '.join(message_links)}")

    context.job_queue.run_once(parties_message_job, when=1)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_sendlists_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/sendlists {utilities.log(update)}")

    events_chat = chats.get_chat(session, Chat.is_events_chat)

    context.bot_data[TempDataKey.FORCE_POST_PARTIES_MESSAGE] = True

    await update.message.reply_html(f"Invio delle nuove liste in {utilities.escape_html(events_chat.title)}...")

    context.job_queue.run_once(parties_message_job, when=1)


HANDLERS = (
    (CommandHandler(["updatelists", "ul"], on_updatelists_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["sendlists", "sl"], on_sendlists_command, filters=ChatFilter.STAFF | Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
