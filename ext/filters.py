import logging

from sqlalchemy.orm import Session
from telegram.ext import filters

from config import config
from database.base import session_scope
from database.models import Chat
from database.queries import chats

logger = logging.getLogger(__name__)


class Filter:
    SUPERADMIN = filters.User(config.telegram.admins)
    SUPERADMIN_AND_GROUP = filters.ChatType.GROUPS & filters.User(config.telegram.admins)
    SUPERADMIN_AND_PRIVATE = filters.ChatType.PRIVATE & filters.User(config.telegram.admins)
    MESSAGE_OR_EDIT = filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE | filters.UpdateType.CHANNEL_POST | filters.UpdateType.EDITED_CHANNEL_POST
    NEW_MESSAGE = filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST
    WITH_TEXT = filters.TEXT | filters.CAPTION


class ChatFilter:
    STAFF = filters.Chat([])
    USERS = filters.Chat([])
    EVENTS = filters.Chat([])


def init_filters():
    logger.debug("initializing filters...")
    with session_scope() as session:
        session: Session

        events_chat: Chat = chats.get_events_chat(session)
        if events_chat:
            logger.debug(f"initializing EVENTS filter ({events_chat.chat_id})...")
            ChatFilter.EVENTS.chat_ids = {events_chat.chat_id}

        staff_chat: Chat = chats.get_staff_chat(session)
        if staff_chat:
            logger.debug(f"initializing STAFF filter ({staff_chat.chat_id})...")
            ChatFilter.STAFF.chat_ids = {staff_chat.chat_id}

        users_chat: Chat = chats.get_users_chat(session)
        if users_chat:
            logger.debug(f"initializing USERS filter ({users_chat.chat_id})...")
            ChatFilter.USERS.chat_ids = {users_chat.chat_id}


init_filters()
