import logging
import pathlib
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, Message, Bot, InlineKeyboardButton, InlineKeyboardMarkup, MessageOriginChannel
from telegram.constants import FileSizeLimit
from telegram.ext import ContextTypes, filters, MessageHandler, CallbackQueryHandler

import decorators
import utilities
from config import config
from constants import Group, TempDataKey
from database.models import Chat, Event, PartiesMessage, DELETION_REASON_DESC, DeletionReason
from database.queries import events, parties_messages, chats
from emojis import Emoji
from ext.filters import ChatFilter, Filter
from plugins.events.common import (
    add_event_message_metadata,
    parse_message_text,
    parse_message_entities,
    drop_events_cache,
    backup_event_media
)

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_linked_group_event_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"evaluation chat: forwarded log channel post {utilities.log(update)}")


HANDLERS = (
    (MessageHandler(ChatFilter.EVALUATION & Filter.IS_AUTOMATIC_FORWARD & ChatFilter.EVALUATION_LOG_GROUP_POST & filters.UpdateType.MESSAGE & Filter.WITH_TEXT, on_linked_group_event_message), Group.PREPROCESS),
)
