import copy
import datetime
import logging
import re
from typing import List, Optional

from sqlalchemy.orm import Session
from telegram import Bot, Message, helpers
from telegram.constants import MessageLimit
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

import decorators
import utilities
from config import config
from constants import BotSettingKey, RegionName, TempDataKey, BotSettingCategory, MONTHS_IT, DeeplinkParam
from database.models import Chat, Event, PartiesMessage, ChatMember
from database.queries import chats, settings, parties_messages, chat_members
from emojis import Flag, Emoji
from plugins.events.common import EventFilter, get_all_events_strings_from_db_group_by, GroupBy, \
    EventFormatting, OrderBy

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
    ListTypeKey.ITALY: [EventFilter.IT, OrderBy.SUBREGION, OrderBy.DATE],
    ListTypeKey.ABROAD: [EventFilter.NOT_IT]
}


def get_events_text(
        session: Session,
        filter_key: str,
        now: datetime.datetime,
        args: List[str],
        bot_username: str,
        send_to_group=False,
        append_bottom_text=True,
        formatting: Optional[EventFormatting] = None
) -> Optional[str]:
    logger.info(f"getting events of type \"{filter_key}\"...")

    # always group by, even if just a week is requested
    args.append(GroupBy.WEEK_NUMBER)

    logger.info(f"args: {args}")
    all_events = get_all_events_strings_from_db_group_by(
        session=session,
        args=args,
        formatting=formatting
    )
    if not all_events:
        return

    events_text = "\n".join(all_events)
    # if we ask for two weeks + group by, the first group by line will start by \n
    events_text = events_text.strip()

    text = f"<b>{LIST_TYPE_DESCRIPTION[filter_key]}</b>\n\n" \
           f"{events_text}"

    if append_bottom_text:
        # include all of this only if the filter_key (that is, the parties list message) is the last one we
        # have to send/edit

        hashtag_current_month = f"#{MONTHS_IT[now.month - 1].lower()}"
        hashtag_next_month = f"#{MONTHS_IT[now.month].lower() if now.month < 12 else MONTHS_IT[0].lower()}"

        radar_deeplink_part = ""
        radar_settings = settings.get_settings_as_dict(session, include_categories=BotSettingCategory.RADAR)
        if radar_settings[BotSettingKey.RADAR_ENABLED].value():
            if radar_settings[BotSettingKey.RADAR_PASSWORD_ENABLED].value():
                radar_deeplink = helpers.create_deep_linked_url(bot_username, payload=DeeplinkParam.RADAR_UNLOCK_TRIGGER)
            else:
                radar_deeplink = helpers.create_deep_linked_url(bot_username, payload=DeeplinkParam.RADAR)
            radar_deeplink_part = f" - oppure <a href=\"{radar_deeplink}\">&lt;&lt;{Emoji.COMPASS}&gt;&gt;</a> ;)"

        request_channel_invite_link_part = ""
        if send_to_group:
            request_link_deeplink = helpers.create_deep_linked_url(bot_username, payload=DeeplinkParam.EVENTS_CHAT_INVITE_LINK)
            request_channel_invite_link_part = f"➜ <i>non riesci ad accedere alle feste linkate? <a href=\"{request_link_deeplink}\">unisciti al canale</a></i>\n"

        freq_minutes = utilities.round_to_hour(config.settings.parties_message_job_frequency)
        refresh_freq = utilities.elapsed_str_from_seconds(freq_minutes * 60, if_empty="pochi minuti")
        newline_or_empty = "\n" if not formatting.collapse else ""  # additional new line if collapse is false
        text += f"{newline_or_empty}\n➜ <i>per una ricerca più approfondita usa gli hashtag {hashtag_current_month} e {hashtag_next_month}, " \
                f"e consulta la <a href=\"https://t.me/c/1926530314/45\">guida alla ricerca tramite hashtag</a>" \
                f"{radar_deeplink_part}</i>\n" \
                f"{request_channel_invite_link_part}" \
                f"➜ <i>aggiornato in automatico (frequenza: {refresh_freq})</i>"

    html_entities_count = utilities.count_html_entities(text)
    additional_entities = 2 if append_bottom_text else 0  # add hashtags to the count
    additional_entities += 1  # just to make sure...
    entities_count = html_entities_count + additional_entities
    logger.debug(f"entities count: {entities_count}/{MessageLimit.MESSAGE_ENTITIES}")
    if entities_count > MessageLimit.MESSAGE_ENTITIES:
        # remove bold entities if we cross the limit
        # this will assume no nested <b> tags
        html_tags_to_remove_count = (entities_count - MessageLimit.MESSAGE_ENTITIES) * 2

        # we want to remove the last <b> entities, but 'count' in re.sub() doesn't work in reverse
        # so we reverse the string (and also the regex, </b> becomes >b/<
        text_reversed = text[::-1]
        text_reversed = re.sub(r">b/?<", "", text_reversed, count=html_tags_to_remove_count)
        text = text_reversed[::-1]

        logger.debug(f"entities count (no bold, {html_tags_to_remove_count} html tags removed): {utilities.count_html_entities(text) + additional_entities}")

    now_str = utilities.format_datetime(now, format_str='%Y%m%d %H%M')
    text += f"\n{utilities.subscript(now_str)} {utilities.subscript(str(entities_count))}"

    return text


async def pin_message(bot: Bot, new_parties_message: Message, old_parties_message: Optional[PartiesMessage] = None):
    logger.info("pinning new message...")
    try:
        await new_parties_message.pin(disable_notification=True)
    except (TelegramError, BadRequest) as e:
        logger.error(f"error while pinning new parties message: {e}")

    if old_parties_message and not old_parties_message.deleted:
        logger.info("unpinning old message...")
        try:
            await bot.unpin_chat_message(old_parties_message.chat_id, old_parties_message.message_id)
        except (TelegramError, BadRequest) as e:
            logger.error(f"error while unpinning old parties message: {e}")


async def delete_old_message(bot: Bot, old_parties_message: PartiesMessage):
    logger.info(f"deleting old parties message {old_parties_message.message_id} of type {old_parties_message.events_type}...")
    success = await utilities.delete_messages_by_id_safe(bot, old_parties_message.chat_id, old_parties_message.message_id)
    logger.info(f"success: {success}")

    old_parties_message.deleted = True


def time_to_post(now_it: datetime.datetime, last_parties_message_isoweek: int, post_weekday: int, post_hour: int):
    current_isoweek = now_it.isocalendar()[1]

    today_is_post_weekday = now_it.weekday() == post_weekday  # whether today is the weekday we should post the message
    new_week = current_isoweek != last_parties_message_isoweek

    logger.info(f"current isoweek: {current_isoweek}, "
                f"last post isoweek: {last_parties_message_isoweek}, "
                f"weekday: {now_it.weekday()} (today_is_post_weekday: {today_is_post_weekday}), "
                f"hour: {now_it.hour} (parties_message_hour: {post_weekday})")

    if today_is_post_weekday and new_week and now_it.hour >= post_hour:
        # post a new message only if it's a different week than the last message's isoweek
        # even if no parties message was posted yet, wait for the correct day and hour
        return True

    return False


@decorators.catch_exception_job()
@decorators.pass_session_job()
async def parties_message_job(context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info("")
    logger.info("parties message job: start")

    pl_settings = settings.get_settings_as_dict(session, include_categories=BotSettingCategory.PARTIES_LIST)

    if not pl_settings[BotSettingKey.PARTIES_LIST].value():
        logger.debug("parties list disabled from settings")
        return

    parties_message_send_to_group = pl_settings[BotSettingKey.PARTIES_LIST_POST_TO_USERS_CHAT].value()
    if not parties_message_send_to_group:
        target_chat: Optional[Chat] = chats.get_chat(session, Chat.is_events_chat)
    else:
        logger.info("using users chat as target chat")
        target_chat: Optional[Chat] = chats.get_chat(session, Chat.is_users_chat)

    if not target_chat:
        logger.debug("no events/users chat set")
    elif target_chat.is_users_chat:
        bot_chat_member: Optional[ChatMember] = chat_members.get_chat_member_by_id(session, context.bot.id, target_chat.chat_id)
        if not (bot_chat_member.is_administrator() and bot_chat_member.can_pin_messages):
            # only admins with the permission to pin messages can edit messages with no time limit
            logger.warning("cannot post to users chat if the bot doesn't have the permission to pin messages")
            return

    parties_message_update_only = pl_settings[BotSettingKey.PARTIES_LIST_UPDATE_ONLY].value()  # whether to use the same messages instad of sending new ones
    parties_message_weekday = pl_settings[BotSettingKey.PARTIES_LIST_WEEKDAY].value()
    parties_message_weeks = pl_settings[BotSettingKey.PARTIES_LIST_WEEKS].value()
    parties_message_hour = pl_settings[BotSettingKey.PARTIES_LIST_HOUR].value()
    parties_message_pin = pl_settings[BotSettingKey.PARTIES_LIST_PIN].value()
    parties_message_delete_old = pl_settings[BotSettingKey.PARTIES_LIST_DELETE_OLD].value()
    parties_message_group_messages_links = pl_settings[BotSettingKey.PARTIES_LIST_DISCUSSION_LINK].value()
    parties_message_collapse = pl_settings[BotSettingKey.PARTIES_LIST_COLLAPSE].value()

    # this flag is set every time something that edits the parties list happens (new/edited event, /delevent...)
    # we need to get it before the for loop because it should be valid for every filter
    parties_list_changed = context.bot_data.pop(TempDataKey.UPDATE_PARTIES_MESSAGE, False)
    logger.info(f"'parties_list_changed': {parties_list_changed}")
    if not parties_list_changed:
        # this flag is set by the /updatelists command: when used, make sure to act as if there has been changes
        parties_list_changed = context.bot_data.pop(TempDataKey.FORCE_UPDATE_PARTIES_MESSAGE, False)
        logger.info(f"force 'parties_list_changed' flag: {parties_list_changed}")

    # we check whether the flag is set once for all filters
    # it is set manually
    post_new_message_force = context.bot_data.pop(TempDataKey.FORCE_POST_PARTIES_MESSAGE, False)
    logger.info(f"'post_new_message_force' from context.bot_data: {post_new_message_force}")

    now_it = utilities.now(tz=True, dst_check=True)

    # we need this so we can add the footer text just to the last message
    last_filter_key = list(PARTIES_MESSAGE_TYPES_ARGS.keys())[-1]

    for filter_key, filter_args in PARTIES_MESSAGE_TYPES_ARGS.items():
        logger.info(f"filter: {filter_key}")
        args = [arg for arg in filter_args]  # create a copy of the args list, because we will add items to it

        last_parties_message: Optional[PartiesMessage] = parties_messages.get_last_parties_message(session, target_chat.chat_id, events_type=filter_key)

        post_new_message = copy.deepcopy(post_new_message_force)  # create a copy, not a reference
        if not post_new_message:
            # we do these checks only if "force" flag was not set
            if not parties_message_update_only or not last_parties_message:
                # we check whether it is time to post only if:
                # - 'update only' mode is off, or
                # - 'update only' mode is on, but we never posted a parties message for this filter
                logger.info(f"'update only' mode is off OR we never sent a parties message for <{filter_key}> in {target_chat.chat_id}: checking whether it is time to post")

                last_parties_message_isoweek = last_parties_message.isoweek() if last_parties_message else 53
                if time_to_post(now_it, last_parties_message_isoweek, parties_message_weekday, parties_message_hour):
                    # post a new message only if it's a different week than the last message's isoweek
                    # even if no parties message was posted yet, wait for the correct day and hour
                    logger.info(f"it's time to post a new message")
                    post_new_message = True
                else:
                    logger.info(f"it's not time to post a new message")
            else:
                logger.info("'update only' mode is on and a 'last_parties_message' exists: if the parties list changed, we will update the existing message")

        if not post_new_message and not parties_list_changed and last_parties_message:
            # if we don't have to post a new message and the parties list didn't change, we have to check whether it is
            # monday: if it's monday and the last time we updated the list was during the past week, we need to
            # force-update it, so it will contain the parties from the correct week
            if last_parties_message.message_edit_date and now_it.weekday() == 0 and last_parties_message.message_edit_date.weekday() != 0:
                logger.info("today is monday and the last time we updated the message was during the past week: "
                            "acting as if the parties list was changed to \"force-update\" the message")
                # this will be used for all filetrs keys, so changing this here will cause all following lists to be updated
                parties_list_changed = True

        if not post_new_message and not parties_list_changed:
            # if it's not time to post a new message and nothing happened that edited
            # the parties list, simply skip this filter
            logger.info("no need to post new message, and the list didn't change: continuing to next filter...")
            continue
        elif not post_new_message and parties_list_changed and not last_parties_message:
            logger.info(f"parties list changed, but there is no parties list message to update and it's not time to post: continuing to next filter...")
            continue

        logger.info("adding arg to extract number of weeks...")
        args.append(EventFilter.WEEK) if parties_message_weeks <= 1 else args.append(EventFilter.WEEK_2)

        text = get_events_text(
            session=session,
            filter_key=filter_key,
            now=now_it,
            args=args,
            bot_username=context.bot.username,
            append_bottom_text=filter_key == last_filter_key,
            send_to_group=parties_message_send_to_group,
            formatting=EventFormatting(discussion_group_link=parties_message_group_messages_links, collapse=parties_message_collapse)
        )
        if not text:
            logger.info("no events for this filter, continuing to next one...")
            continue

        # no idea why but we *need* large timeouts for these requests
        timeouts = dict(connect_timeout=300, read_timeout=300, write_timeout=300)

        if post_new_message:
            logger.info("posting new message...")
            sent_message = await context.bot.send_message(target_chat.chat_id, text, **timeouts)

            logger.info("saving new PartiesMessage...")
            new_parties_message = PartiesMessage(sent_message, events_type=filter_key, force_sent=post_new_message_force)
            new_parties_message.force_sent = post_new_message_force
            session.add(new_parties_message)
            session.commit()

            if parties_message_pin:
                await pin_message(context.bot, sent_message, last_parties_message)
            if parties_message_delete_old and last_parties_message:
                await delete_old_message(context.bot, last_parties_message)
        elif parties_list_changed and last_parties_message:
            # 'last_parties_message' should always be ok (not None) inside this 'if'
            logger.info(f"editing message {last_parties_message.message_id} in chat {last_parties_message.chat_id}...")
            edited_message = await context.bot.edit_message_text(text, last_parties_message.chat_id, last_parties_message.message_id, **timeouts)
            last_parties_message.save_edited_message(edited_message)

        session.commit()

