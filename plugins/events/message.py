import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, filters, MessageHandler

from .common import Filter, add_event_message_metadata, parse_message_text, parse_message_entities
from ext.filters import ChatFilter
from database.models import Chat
from database.queries import events, chats
import decorators
import utilities
from constants import Group

logger = logging.getLogger(__name__)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_event_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"events chat message update {utilities.log(update)}")

    if "origin_fwd" in context.bot_data and update.effective_message.forward_from_chat:
        logger.debug("saved forwarded message data")
        chat_id = update.effective_message.forward_from_chat.id
        message_id = update.effective_message.forward_from_message_id

        # save origin chat
        chats.get_safe(session, update.effective_message.forward_from_chat)
    else:
        chat_id = update.effective_chat.id
        message_id = update.effective_message.message_id

    event = events.get_or_create(session, chat_id, message_id)
    if event.deleted:
        logger.debug(f"event ({event.chat_id}; {event.message_id}) was deleted: skipping update")
        return

    add_event_message_metadata(update.effective_message, event)
    parse_message_entities(update.effective_message, event)
    parse_message_text(update.effective_message.text or update.effective_message.caption, event)

    logger.info(f"parsed event: {event}")

    session.commit()


HANDLERS = (
    (MessageHandler(ChatFilter.EVENTS & Filter.UPDATE_TYPE & Filter.WITH_TEXT, on_event_message), Group.PREPROCESS),
)
