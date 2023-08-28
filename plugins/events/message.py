import json
import logging
import pathlib

from sqlalchemy.orm import Session
from telegram import Update, Message
from telegram.ext import ContextTypes, filters, MessageHandler

from .common import add_event_message_metadata, parse_message_text, parse_message_entities, drop_events_cache
from ext.filters import ChatFilter, Filter
from database.models import Chat, Event
from database.queries import events, chats
import decorators
import utilities
from constants import Group
from config import config

logger = logging.getLogger(__name__)


async def download_event_media(message: Message):
    if not message.photo and not message.video and not message.animation:
        logger.debug(f"no media to backup")
        return

    if not message.edit_date:
        file_name = f"{message.message_id}"
    else:
        edit_timestamp = int(message.edit_date.timestamp())
        file_name = f"{message.message_id}_edit_{edit_timestamp}"

    if message.photo:
        file_name = f"{file_name}.jpg"
    elif message.video or message.animation:
        file_name = f"{file_name}.mp4"

    file_path = pathlib.Path("events_data") / file_name

    logger.info(f"downloading to {file_path}...")
    if message.photo:
        new_file = await message.effective_attachment[-1].get_file()
    else:
        new_file = await message.effective_attachment.get_file()

    await new_file.download_to_drive(file_path)


async def backup_event_media(update: Update, event: Event):
    # edited_messages: do not download the media if it was not modified
    if update.edited_message:
        m = update.edited_message
        new_file_unique_id = m.photo[-1].file_unique_id if m.photo else m.effective_attachment.file_unique_id
        if new_file_unique_id == event.media_file_unique_id:
            logger.debug(
                f"edited event message: file_unique_id ({new_file_unique_id}) didn't change, skipping media download")
            return False

    try:
        await download_event_media(update.effective_message)
        return True
    except Exception as e:
        logger.error(f"error while trying to download media: {e}", exc_info=True)
        return False


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_event_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"events chat message update {utilities.log(update)}")

    # chat_id = update.effective_message.forward_from_chat.id
    # message_id = update.effective_message.forward_from_message_id

    chat_id = update.effective_chat.id
    message_id = update.effective_message.message_id

    event: Event = events.get_or_create(session, chat_id, message_id)
    if event.deleted:
        logger.debug(f"event ({event.chat_id}; {event.message_id}) was deleted: skipping update")
        return

    add_event_message_metadata(update.effective_message, event)
    parse_message_entities(update.effective_message, event)
    parse_message_text(update.effective_message.text or update.effective_message.caption, event)

    logger.info(f"parsed event: {event}")

    logger.info("dropping events cache...")
    drop_events_cache(context)

    session.commit()

    if config.settings.backup_events:
        await backup_event_media(update, event)


@decorators.catch_exception(silent=True)
@decorators.pass_session()
async def on_linked_group_event_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"discussion group: events chat message update {utilities.log(update)}")

    channel_chat_id = update.message.sender_chat.id
    channel_message_id = update.message.forward_from_message_id
    event: Event = events.get_or_create(session, channel_chat_id, channel_message_id)
    if not event:
        logger.warning(f"received discussion group channel post message, but no Event was found ({channel_chat_id}, {channel_message_id})")
        return

    logger.info("saving discussion group's post info...")
    event.save_discussion_group_message(update.message)

    # make sure to drop the event cache so new commands will have updated info
    logger.info("dropping events cache...")
    drop_events_cache(context)


HANDLERS = (
    (MessageHandler(ChatFilter.EVENTS & Filter.MESSAGE_OR_EDIT & Filter.WITH_TEXT, on_event_message), Group.PREPROCESS),
    (MessageHandler(filters.ChatType.GROUPS & ChatFilter.EVENTS_GROUP_POST & filters.UpdateType.MESSAGE & Filter.WITH_TEXT, on_linked_group_event_message), Group.PREPROCESS),
)
