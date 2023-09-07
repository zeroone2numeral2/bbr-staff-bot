import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler

import decorators
import utilities
from constants import Group
from ext.filters import ChatFilter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_coordinates(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"coordinates {utilities.log(update)}")
    return


HANDLERS = (
    (MessageHandler(ChatFilter.STAFF | ChatFilter.USERS, on_coordinates), Group.NORMAL),
)
