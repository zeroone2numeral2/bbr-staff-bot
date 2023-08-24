import logging
import re
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, MessageId
from telegram.constants import ChatAction
from telegram.error import TelegramError, BadRequest
from telegram.ext import filters, ContextTypes, MessageHandler
from telegram.ext.filters import MessageFilter

from constants import Group
from database.models import UserMessage, AdminMessage, User, Chat, PrivateChatMessage
from database.queries import user_messages, admin_messages, users, private_chat_messages
import decorators
import utilities
from emojis import Emoji
from ext.filters import ChatFilter
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_coordinates(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"coordinates {utilities.log(update)}")
    return


HANDLERS = (
    (MessageHandler(ChatFilter.STAFF | ChatFilter.USERS, on_coordinates), Group.NORMAL),
)
