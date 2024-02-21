import logging
import pathlib
import re
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, Message, Bot, InlineKeyboardButton, InlineKeyboardMarkup, MessageOriginChannel
from telegram.constants import FileSizeLimit
from telegram.ext import ContextTypes, filters, MessageHandler, CallbackQueryHandler

import decorators
import utilities
from config import config
from constants import Group, TempDataKey
from database.models import Chat, Event, PartiesMessage, DELETION_REASON_DESC, DeletionReason, ApplicationRequest
from database.queries import events, parties_messages, chats, application_requests
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

    log_message_chat_id = update.message.sender_chat.id
    log_message_message_id = update.message.forward_origin.message_id

    request: Optional[ApplicationRequest] = application_requests.get_from_log_channel_message(session, log_message_chat_id, log_message_message_id)
    if not request:
        logger.warning(f"couldn't find any application request for log channel message {log_message_message_id}")
        if update.effective_message.text and re.search(r"#rid\d+", update.effective_message.text, re.I):
            # send the warning message only if the hashtag is found
            await update.effective_message.reply_html(f"{Emoji.WARNING} impossibile trovare richieste per questo messaggio")
        return


HANDLERS = (
    (MessageHandler(ChatFilter.EVALUATION & Filter.IS_AUTOMATIC_FORWARD & ChatFilter.EVALUATION_LOG_GROUP_POST & filters.UpdateType.MESSAGE & Filter.WITH_TEXT, on_linked_group_event_message), Group.PREPROCESS),
)
