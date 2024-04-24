import logging
import pathlib
import re
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update, Message, Bot, InlineKeyboardButton, InlineKeyboardMarkup, MessageOriginChannel
from telegram.constants import FileSizeLimit, MessageLimit, MediaGroupLimit
from telegram.error import BadRequest
from telegram.ext import ContextTypes, filters, MessageHandler, CallbackQueryHandler

import decorators
import utilities
from config import config
from constants import Group, TempDataKey
from database.models import Chat, Event, PartiesMessage, DELETION_REASON_DESC, DeletionReason, ApplicationRequest, \
    DescriptionMessageType, DescriptionMessage
from database.queries import events, parties_messages, chats, application_requests
from emojis import Emoji
from ext.filters import ChatFilter, Filter
from plugins.events.common import (
    add_event_message_metadata,
    parse_message_text,
    parse_message_entities,
    drop_events_cache,
    backup_event_media
)

logger = logging.getLogger(__name__)


async def send_attachment_comments(message: Message, request: ApplicationRequest):
    # we will save the whole list of attachments we sent just in case we will need to link them,
    # but we actually need just the first one (because it's the message we reply to)
    sent_attachment_messages: List[Message] = []

    messages_to_send_as_album: List[DescriptionMessage] = []
    text_messages_to_merge: List[DescriptionMessage] = []
    single_media_messages: List[DescriptionMessage] = []

    # in this loop we populate the lists we initialized above
    description_message: DescriptionMessage
    for description_message in request.description_messages:
        if description_message.is_social_message() or description_message.is_other_members_message():
            # we include them in the log/staff message with the user's details
            continue

        if description_message.can_be_grouped():
            messages_to_send_as_album.append(description_message)
            continue

        if description_message.text:
            # sent_message = await bot.send_message(log_chat_id, description_message.text_html)
            text_messages_to_merge.append(description_message)
            continue

        if description_message.type in (DescriptionMessageType.VOICE, DescriptionMessageType.VIDEO_MESSAGE):
            single_media_messages.append(description_message)
            continue

        logger.warning(f"unexpected description message: {description_message}")

    # no idea why but we *need* large timeouts
    timeouts = dict(connect_timeout=300, read_timeout=300, write_timeout=300)

    # merge and send all DescriptionMessage that contain the text the user sent as presentation
    logger.debug("merging and sending presentation text messages...")
    merged_text = f"{Emoji.SHEET} <b>presentazione</b>"
    merged_text_includes = []  # list of indexes of the DescriptionMessage that have been merged into the current merged_text
    for i, description_message in enumerate(text_messages_to_merge):
        if len(merged_text) + len(description_message.text_html) > MessageLimit.MAX_TEXT_LENGTH:
            sent_message = await message.reply_html(merged_text, do_quote=True, **timeouts)
            sent_attachment_messages.append(sent_message)
            for j in merged_text_includes:
                # save the message we just sent as the log message for each one of the DescriptionMessage that were merged into it
                text_messages_to_merge[j].set_log_comment_message(sent_message)

            merged_text = ""
            merged_text_includes = []
        else:
            merged_text += f"\n\n{description_message.text_html}"
            merged_text_includes.append(i)

    # send what's left, if anything
    if merged_text:
        logger.debug("sending what's left...")
        sent_message = await message.reply_html(merged_text, do_quote=True, **timeouts)
        sent_attachment_messages.append(sent_message)
        for i in merged_text_includes:
            # save the message we just sent as the log message for each one of the DescriptionMessage that were merged into it
            text_messages_to_merge[i].set_log_comment_message(sent_message)

    # merge into an album and send all DescriptionMessage that can be grouped into an album
    logger.debug("merging and sending presentation media messages that fit into albums...")
    input_medias = []
    for i, description_message in enumerate(messages_to_send_as_album):
        input_medias.append(description_message.get_input_media())

        if len(input_medias) == MediaGroupLimit.MAX_MEDIA_LENGTH:
            logger.debug("album limit reached: sending media group...")
            sent_messages = await message.reply_media_group(input_medias, do_quote=True, **timeouts)
            sent_attachment_messages.append(sent_messages[0])  # we will link just the first one
            # save sent log message
            for j, sent_message in enumerate(sent_messages):
                index = int(i / MediaGroupLimit.MAX_MEDIA_LENGTH) + j
                logger.debug(f"saving log message with index {index}...")
                messages_to_send_as_album[index].set_log_comment_message(sent_message)

            input_medias = []

    # send what's left, if anything
    medias_count = len(input_medias)
    if input_medias:
        logger.debug(f"sending what's left ({input_medias})...")
        sent_messages = await message.reply_media_group(input_medias, do_quote=True, **timeouts)
        sent_attachment_messages.append(sent_messages[0])  # we will link just the first one
        for i, sent_message in enumerate(sent_messages):
            index = (medias_count - i) * -1  # go through the list from the last item
            logger.debug(f"saving log message with index {index}...")
            messages_to_send_as_album[index].set_log_comment_message(sent_message)

    # send all DescriptionMessage that are a media and cannot be grouped
    logger.debug("sending presentation text messages that should be sent on their own...")
    for description_message in single_media_messages:
        if description_message.type == DescriptionMessageType.VOICE:
            sent_message = await message.reply_voice(description_message.media_file_id, caption=description_message.caption_html, do_quote=True)
        elif description_message.type == DescriptionMessageType.VIDEO_MESSAGE:
            sent_message = await message.reply_video_note(description_message.media_file_id, do_quote=True)
        else:
            continue

        description_message.set_log_comment_message(sent_message)
        sent_attachment_messages.append(sent_message)


@decorators.catch_exception()
@decorators.pass_session()
async def on_linked_group_event_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"evaluation chat: forwarded log channel post {utilities.log(update)}")

    message: Message = update.effective_message

    log_message_chat_id = message.sender_chat.id
    log_message_message_id = message.forward_origin.message_id

    request: Optional[ApplicationRequest] = application_requests.get_from_log_channel_message(session, log_message_chat_id, log_message_message_id)
    if not request:
        logger.warning(f"couldn't find any application request for log channel message {log_message_message_id}")
        if not message.reply_to_message and message.text and re.search(rf"{ApplicationRequest.REQUEST_ID_HASHTAG_PREFIX}\d+", message.text, re.I):
            # send the warning message only if the hashtag is found
            await message.reply_html(f"{Emoji.WARNING} impossibile trovare richieste per questo messaggio", do_quote=True)

        # checking whether the message is the log channel message that contains the inline keyboard to evaluate the request
        # if so, we delete the message automatically forwarded in the evaluation chat
        request_from_evaluation_message: Optional[ApplicationRequest] = application_requests.get_from_evaluation_buttons_log_channel_message(session, log_message_chat_id, log_message_message_id)
        if request_from_evaluation_message:
            logger.info("log message with evaluation buttons forwarded to the evaluation chat: deleting...")
            await utilities.delete_messages_safe(message)

        return

    logger.info(f"saving staff chat message...")
    request.set_staff_message(message)
    session.commit()

    await send_attachment_comments(message, request)

    logger.info(f"unpinning log message from evaluation chat...")
    try:
        await message.unpin()
    except BadRequest as e:
        logger.info(f"error while unpinning: {e}")


HANDLERS = (
    (MessageHandler(ChatFilter.EVALUATION & Filter.IS_AUTOMATIC_FORWARD & ChatFilter.EVALUATION_LOG_GROUP_POST & filters.UpdateType.MESSAGE & Filter.WITH_TEXT, on_linked_group_event_message), Group.PREPROCESS),
)
