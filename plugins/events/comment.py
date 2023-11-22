import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, Message
from telegram.ext import MessageHandler, ContextTypes

import decorators
import utilities
from constants import Group
from database.models import Chat, Event, User
from database.queries import events
from ext.filters import ChatFilter, Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True, pass_user=True)
async def on_channel_comment(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat, user: User):
    logger.info(f"users chat message with thread_id {update.effective_message.message_thread_id} {utilities.log(update)}")

    message: Message = update.effective_message
    if message.edit_date:
        logger.info("edited message: getting existing ChannelComment...")
        # channel_comment: ChannelComment = channel_comments.get(session, message)
        # return if none
    else:
        event: Optional[Event] = events.get_event_from_discussion_group_message(session, update.effective_message)
        if not event:
            # the update will continue the propagation because it's pre-process
            return

        logger.info("creating new ChannelComment...")
        # ChannelComment(event)

    logger.info("saving/updating ChannelComment data...")
    # channel_comment.save_message(message)


HANDLERS = (
    (MessageHandler(ChatFilter.USERS & Filter.MESSAGE_OR_EDIT & Filter.BELONGS_TO_THREAD, on_channel_comment), Group.PREPROCESS),
)
