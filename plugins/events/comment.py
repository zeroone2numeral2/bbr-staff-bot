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

logger = logging.getLogger(__name__)


@decorators.catch_exception(silent=True)
@decorators.pass_session()
async def on_channel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"users chat message with thread_id {update.effective_message.message_thread_id} {utilities.log(update)}")

    message: Message = update.effective_message
    create = True
    if message.edit_date:
        logger.info("edited message: getting existing ChannelComment...")
        channel_comment: ChannelComment = channel_comments.get(session, message.chat.id, message.message_id)
        if channel_comment:
            create = False
        else:
            logger.info("...ChannelComment not found: we will create it")

    if create:
        event: Optional[Event] = events.get_event_from_discussion_group_message(session, message)
        if not event:
            logger.info(f"no event found for message with thread_id {message.message_thread_id}")
            return

        if event.deleted:
            logger.info(f"skipping comment under deleted event")
            return

        logger.info("creating new ChannelComment...")
        channel_comment = ChannelComment(message, event, save_message=False)
        session.add(channel_comment)

    logger.info("saving/updating ChannelComment data...")
    channel_comment.save_message(message)


HANDLERS = (
    (MessageHandler(ChatFilter.USERS & Filter.MESSAGE_OR_EDIT & Filter.BELONGS_TO_THREAD, on_channel_comment), Group.PREPROCESS),
)
