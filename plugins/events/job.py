import datetime
import logging
import re
from typing import List, Optional

from sqlalchemy.orm import Session
from telegram import Bot, Message
from telegram.constants import MessageLimit
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

import decorators
import utilities
from config import config
from constants import BotSettingKey, RegionName, TempDataKey
from database.models import Chat, Event, PartiesMessage
from database.queries import chats, events, settings, parties_messages
from emojis import Flag, Emoji
from plugins.events.common import format_event_string, EventFilter, get_all_events_strings_from_db_group_by, GroupBy

logger = logging.getLogger(__name__)


class ListTypeKey:
    ITALY = "italy"
    ABROAD = "abroad"


LIST_TYPE_DESCRIPTION = {
    ListTypeKey.ITALY: f"{Flag.ITALY} Feste in Italia",
    ListTypeKey.ABROAD: f"{Emoji.EARTH} Feste all'estero"
}


IT_REGIONS = [RegionName.ITALIA, RegionName.CENTRO_ITALIA, RegionName.NORD_ITALIA, RegionName.SUD_ITALIA]

# we will post a channel message for each of these lists types
PARTIES_MESSAGE_TYPES = {
    ListTypeKey.ITALY: [Event.region.in_(IT_REGIONS)],
    ListTypeKey.ABROAD: [Event.region.not_in(IT_REGIONS)]
}

# we will post a channel message for each of these lists types
PARTIES_MESSAGE_TYPES_ARGS = {
    ListTypeKey.ITALY: [EventFilter.IT],
    ListTypeKey.ABROAD: [EventFilter.NOT_IT]
}


def get_events_text(session: Session, filter_key: str, now: datetime.datetime, args: List[str]) -> str:
    logger.info(f"getting events of type \"{filter_key}\"...")

    # always group by, even if just a week is requested
    args.append(GroupBy.WEEK_NUMBER)

    weeks = settings.get_or_create(session, BotSettingKey.PARTIES_LIST_WEEKS).value()
    if weeks <= 1:
        args.append(EventFilter.WEEK)
    else:
        args.append(EventFilter.WEEK_2)

    logger.info(f"args: {args}")
    all_events = get_all_events_strings_from_db_group_by(session, args)

    events_text = "\n".join(all_events)
    # if we ask for two weeks + group by, the first group by line will start by \n
    events_text = events_text.strip()

    text = f"<b>{LIST_TYPE_DESCRIPTION[filter_key]}</b>\n\n{events_text}"
    now_str = utilities.format_datetime(now, format_str='%Y%m%d %H%M')
    text += f"\n\n{utilities.subscript(now_str)}"

    entities_count = utilities.count_html_entities(text)
    logger.debug(f"entities count: {entities_count}/{MessageLimit.MESSAGE_ENTITIES}")
    if entities_count > MessageLimit.MESSAGE_ENTITIES:
        # remove bold entities if we cross the limit
        text = re.sub(r"</?b>", "", text)
        logger.debug(f"entities count (no bold): {utilities.count_html_entities(text)}/{MessageLimit.MESSAGE_ENTITIES}")

    return text


async def pin_message(bot: Bot, new_parties_message: Message, old_parties_message: Optional[PartiesMessage] = None):
    logger.info("pinning new message...")
    try:
        await new_parties_message.pin(disable_notification=True)
    except (TelegramError, BadRequest) as e:
        logger.error(f"error while pinning new parties message: {e}")

    if old_parties_message:
        logger.info("unpinning old message...")
        try:
            await bot.unpin_chat_message(old_parties_message.chat_id, old_parties_message.message_id)
        except (TelegramError, BadRequest) as e:
            logger.error(f"error while unpinning old parties message: {e}")


@decorators.catch_exception_job()
@decorators.pass_session_job()
async def parties_message_job(context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info("parties message job")

    events_chat = chats.get_chat(session, Chat.is_events_chat)
    if not events_chat:
        logger.debug("no events chat set")
        return

    parties_list_enabled = settings.get_or_create(session, BotSettingKey.PARTIES_LIST).value()
    if not parties_list_enabled:
        logger.debug("parties list disabled from settings")
        return

    # this flag is set every time something that edits the parties list happens (new/edited event, /delevent...)
    # we need to get it before the for loop because it should be valid for every filter
    update_existing_message = context.bot_data.pop(TempDataKey.UPDATE_PARTIES_MESSAGE, False)

    # we check whether the flag is set once for every filter
    # it is set manually
    post_new_message_force = context.bot_data.pop(TempDataKey.FORCE_POST_PARTIES_MESSAGE, None)

    now = utilities.now(tz=True)

    for filter_key, args in PARTIES_MESSAGE_TYPES_ARGS.items():
        logger.info(f"filter: {filter_key}")

        current_isoweek = now.isocalendar()[1]
        last_parties_message = parties_messages.get_last_parties_message(session, events_chat.chat_id, events_type=filter_key)
        last_parties_message_isoweek = 53 if not last_parties_message else last_parties_message.isoweek()

        post_new_message = False

        today_is_post_weekday = now.weekday() == config.settings.parties_message_weekday  # whether today is the weekday we should post the message
        new_week = current_isoweek != last_parties_message_isoweek
        logger.info(f"current isoweek: {current_isoweek}, "
                    f"last post isoweek: {last_parties_message_isoweek}, "
                    f"weekday: {now.weekday()}, "
                    f"hour: {now.hour}")

        if today_is_post_weekday and new_week and now.hour >= config.settings.parties_message_hour:
            # post a new message only if it's a different week than the last message's isoweek
            # even if no parties message was posted yet, wait for the correct day and hour
            logger.info(f"it's time to post")
            post_new_message = True
        elif post_new_message_force:
            logger.info("force-post new message flag was true: time to post a new message")
            post_new_message = True

        if not post_new_message and not update_existing_message:
            # if it's not time to post a new message and nothing happened that edited
            # the parties list ('update_existing_message'), simply skip this filter
            logger.info("no need to post new message or update the existing one: continuing to next filter...")
            continue

        text = get_events_text(session, filter_key, now, args)

        if post_new_message:
            logger.info("posting new message...")
            sent_message = await context.bot.send_message(events_chat.chat_id, text)

            logger.info("saving new PartiesMessage...")
            new_parties_message = PartiesMessage(sent_message, events_type=filter_key)
            new_parties_message.force_sent = post_new_message_force
            session.add(new_parties_message)
            session.commit()

            if config.settings.parties_message_pin:
                await pin_message(context.bot, sent_message, last_parties_message)
        elif update_existing_message:
            logger.info(f"editing message {last_parties_message.message_id} in chat {last_parties_message.chat_id}...")
            edited_message = await context.bot.edit_message_text(text, last_parties_message.chat_id, last_parties_message.message_id)
            last_parties_message.save_edited_message(edited_message)
            session.commit()

