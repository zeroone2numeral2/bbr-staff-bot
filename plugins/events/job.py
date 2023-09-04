import datetime
import logging

from sqlalchemy.orm import Session
from telegram.ext import ContextTypes

from database.base import get_session
from database.models import Chat, Event, PartiesMessage
from database.models import BotSetting
from database.queries import chats, events, settings, parties_messages
import utilities
from constants import Language, BOT_SETTINGS_DEFAULTS, BotSettingKey, RegionName, TempDataKey
from config import config
from plugins.events.common import format_event_string

logger = logging.getLogger(__name__)


class FilterKey:
    ITALY = "italy"
    ABROAD = "abroad"


FILTER_DESCRIPTION = {
    FilterKey.ITALY: "Feste ini Italia",
    FilterKey.ABROAD: "Feste all'estero"
}


async def parties_message_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("parties message job")
    session: Session = get_session()

    events_chat = chats.get_chat(session, Chat.is_events_chat)
    if not events_chat:
        logger.debug("no events chat set")
        return

    parties_list_enabled = settings.get_or_create(session, BotSettingKey.PARTIES_LIST).value()
    if not parties_list_enabled:
        logger.debug("parties list disabled from settings")
        return

    # this flag is set every time an event that edited the parties list is received
    # we need to get it before the for loop because it's valid for every filter
    update_existing_message = context.bot_data.pop(TempDataKey.UPDATE_PARTIES_MESSAGE, False)

    now = utilities.now()
    it_regions = [RegionName.ITALIA, RegionName.CENTRO_ITALIA, RegionName.NORD_ITALIA, RegionName.SUD_ITALIA]

    # we will post a channel message for each of these filters
    parties_message_filters = {
        FilterKey.ITALY: [Event.region.in_(it_regions)],
        FilterKey.ABROAD: [Event.region.not_in(it_regions)]
    }

    for filter_key, filters in parties_message_filters.items():
        logger.info(f"checking {filter_key}...")

        current_isoweek = now.isocalendar()[1]
        last_parties_message = parties_messages.get_last_parties_message(session, events_chat.chat_id,
                                                                         events_type=filter_key)

        post_new_message = False

        today_is_post_weekday = now.weekday() == config.settings.parties_message_weekday  # whether today is the weekday we should post the message
        week_changed = current_isoweek != last_parties_message.isoweek()
        if not last_parties_message:
            logger.info("no last parties message: it's time to post a new one")
            post_new_message = True
        elif today_is_post_weekday and week_changed and now.hour >= config.settings.parties_message_hour:
            logger.info(f"time to post, current isoweek: {current_isoweek}, last post isoweek: "
                        f"{last_parties_message.isoweek()}, weekday: {now.weekday()}, hour: {now.hour}")
            post_new_message = True

        if not post_new_message and not update_existing_message:
            logger.info("no need to post new message or update the existing one: continuing to next filter...")
            continue

        logger.info(f"getting events of type \"{filter_key}\"...")
        week_events, from_date, next_monday = events.get_week_events(session, now, filters)
        to_date = next_monday + datetime.timedelta(-1)

        from_str = utilities.format_datetime(from_date, format_str='%d/%m/%Y')
        to_str = utilities.format_datetime(to_date, format_str='%d/%m/%Y')
        text = f"<b>{FILTER_DESCRIPTION[filter_key]}, dal {from_str} al {to_str}:</b>"
        event: Event
        for event in week_events:
            text += f"\n{format_event_string(event)}"

        text += f"\n\nUltimo aggiornamento: {utilities.format_datetime(now, format_str='%d/%m/%Y')}"

        if post_new_message:
            logger.info("posting new message...")
            sent_message = await context.bot.send_message(events_chat.chat_id, text)
            new_parties_message = PartiesMessage(sent_message)
            session.add(new_parties_message)
            session.commit()
        elif update_existing_message:
            logger.info(f"editing message {last_parties_message.message_id} in chat {last_parties_message.chat_id}...")
            edited_message = await context.bot.edit_message_text(text, last_parties_message.chat_id, last_parties_message.message_id)
            last_parties_message.save_message_edit(edited_message)

