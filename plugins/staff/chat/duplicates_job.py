import datetime
import logging

from sqlalchemy.orm import Session
from telegram.ext import ContextTypes

import decorators
import utilities
from database.queries import staff_chat_messages

logger = logging.getLogger(__name__)


@decorators.catch_exception_job()
@decorators.pass_session_job()
async def delete_old_messages_job(context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info("delete old messages job: start")

    days = 30 * 3
    now = utilities.now()
    older_than = now - datetime.timedelta(days=days)
    logger.info(f"now: {now}, days: {days}, older than: {older_than}")

    deleted_count = staff_chat_messages.delete_old_messages(session, older_than)
    logger.info(f"deleted {deleted_count} records")
