import logging
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from database.base import session_scope
from database.models import Chat, Event, User
from database.queries import settings, events
import decorators
import utilities
from constants import BotSettingKey, Group, Regex, REGIONS_DATA
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/events {utilities.log(update)}")

    events_list: List[Event] = events.get_events(session)
    text_lines = []
    for i, event in enumerate(events_list):
        if not event.is_valid():
            logger.info(f"skipping invalid event: {event}")
            continue

        region_icon = ""
        if event.region and event.region in REGIONS_DATA:
            region_icon = REGIONS_DATA[event.region]["emoji"]

        title_escaped = utilities.escape_html(event.event_title)
        text_line = f"{event.icon()}{region_icon} <b>{title_escaped}</b> ({event.pretty_date()}) • <a href=\"{event.message_link()}\">fly & info</a>"
        text_lines.append(text_line)

        if i > 49:
            # max 100 entities per message
            break

    await update.message.reply_text("\n".join(text_lines))


HANDLERS = (
    (CommandHandler("events", on_events_command), Group.NORMAL),
)
