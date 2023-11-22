import logging
import re

from sqlalchemy.orm import Session
from telegram.ext import filters
from telegram.ext.filters import MessageFilter

import utilities
from config import config
from database.base import session_scope
from database.models import Chat
from database.queries import chats

logger = logging.getLogger(__name__)


class FilterReplyToBot(MessageFilter):
    def __init__(self):
        super().__init__()
        if utilities.is_test_bot():
            self.bot_id = 6217274130
        else:
            self.bot_id = 6171174621

    def filter(self, message):
        if (message.reply_to_message
                and message.reply_to_message.from_user
                and message.reply_to_message.from_user.id == self.bot_id):
            return True

        return False


class FilterReplyTopicsAware(MessageFilter):
    def filter(self, message):
        # messages sent in a topic, when they are *not* a reply to a message, are sent as reply
        # to the "forum_topic_created" service message, so we need to ignore this case
        return message.reply_to_message and not message.reply_to_message.forum_topic_created


class FilterAlbumMessage(MessageFilter):
    def filter(self, message):
        # message is part of an album
        return bool(message.media_group_id)


class FilterBelongsToThread(MessageFilter):
    def filter(self, message):
        # message belongs to a thread
        return bool(message.message_thread_id)


class FilterRadarPassword(MessageFilter):
    def filter(self, message):
        if not config.settings.radar_password or not message.text:
            return False

        return bool(re.search(config.settings.radar_password, message.text, re.I))


class Filter:
    SUPERADMIN = filters.User(config.telegram.admins)
    SUPERADMIN_AND_GROUP = filters.ChatType.GROUPS & filters.User(config.telegram.admins)
    SUPERADMIN_AND_PRIVATE = filters.ChatType.PRIVATE & filters.User(config.telegram.admins)
    MESSAGE_OR_EDIT = filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE | filters.UpdateType.CHANNEL_POST | filters.UpdateType.EDITED_CHANNEL_POST
    NEW_MESSAGE = filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST
    WITH_TEXT = filters.TEXT | filters.CAPTION
    REPLY_TO_BOT = FilterReplyToBot()
    REPLY_TOPICS_AWARE = FilterReplyTopicsAware()
    ALBUM_MESSAGE = FilterAlbumMessage()
    BELONGS_TO_THREAD = FilterBelongsToThread()
    RADAR_PASSWORD = FilterRadarPassword()
    FLY_MEDIA_DOWNLOAD = filters.PHOTO | filters.VIDEO | filters.ANIMATION  # media we can consider as fly, for backups


class ChatFilter:
    STAFF = filters.Chat([])
    EVALUATION = filters.Chat([])
    USERS = filters.Chat([])
    EVENTS = filters.Chat([])
    EVENTS_GROUP_POST = filters.SenderChat([])  # filter to catch EVENTS post in the linked group


def init_filters():
    logger.debug("initializing filters...")
    with session_scope() as session:
        session: Session

        events_chat: Chat = chats.get_chat(session, Chat.is_events_chat)
        if events_chat:
            logger.debug(f"initializing EVENTS filter ({events_chat.chat_id})...")
            ChatFilter.EVENTS.chat_ids = {events_chat.chat_id}
            ChatFilter.EVENTS_GROUP_POST.chat_ids = {events_chat.chat_id}

        staff_chat: Chat = chats.get_chat(session, Chat.is_staff_chat)
        if staff_chat:
            logger.debug(f"initializing STAFF filter ({staff_chat.chat_id})...")
            ChatFilter.STAFF.chat_ids = {staff_chat.chat_id}

        evaluation_chat: Chat = chats.get_chat(session, Chat.is_evaluation_chat)
        if evaluation_chat:
            logger.debug(f"initializing EVALUATION filter ({evaluation_chat.chat_id})...")
            ChatFilter.EVALUATION.chat_ids = {evaluation_chat.chat_id}

        users_chat: Chat = chats.get_chat(session, Chat.is_users_chat)
        if users_chat:
            logger.debug(f"initializing USERS filter ({users_chat.chat_id})...")
            ChatFilter.USERS.chat_ids = {users_chat.chat_id}


init_filters()
