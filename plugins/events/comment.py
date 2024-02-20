import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, Message
from telegram.ext import MessageHandler, ContextTypes

import decorators
import utilities
from constants import Group
from database.models import Chat, Event, User, ChannelComment
from database.queries import events, channel_comments
from ext.filters import ChatFilter, Filter
from plugins.events.common import backup_event_media
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_channel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User, chat: Chat):
    logger.info(f"users chat message with thread_id {update.effective_message.message_thread_id} {utilities.log(update)}")

    message: Message = update.effective_message
    channel_comment = None

    if message.edit_date:
        logger.info("edited message: getting existing ChannelComment...")
        channel_comment: Optional[ChannelComment] = channel_comments.get(session, message.chat.id, message.message_id)

    if not channel_comment:
        event: Optional[Event] = events.get_event_from_discussion_group_message(session, message)
        if not event:
            logger.info(f"no event found for message with thread_id {message.message_thread_id}")
            return

        if event.deleted:
            logger.info(f"skipping comment under deleted event")
            return

        logger.info("creating new ChannelComment...")
        channel_comment = ChannelComment(message.chat.id, message.message_id, event)
        session.add(channel_comment)

    logger.info("saving/updating ChannelComment data...")
    channel_comment.save_message(message)

    if config.settings.backup_events and not channel_comment.not_info:
        # do not download if a message is marked as "not info"
        await backup_event_media(update)


HANDLERS = (
    (MessageHandler(ChatFilter.USERS & Filter.MESSAGE_OR_EDIT & Filter.BELONGS_TO_THREAD, on_channel_comment), Group.PREPROCESS),
)
