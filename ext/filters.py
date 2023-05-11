import logging

from sqlalchemy.orm import Session
from telegram.ext import filters

from config import config
from constants import BotSettingKey
from database.base import session_scope
from database.models import BotSetting, Chat
from database.queries import settings, chats

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

        setting: BotSetting = settings.get_or_create(session, BotSettingKey.EVENTS_CHAT_ID)
        if not setting.value():
            logger.debug(f"setting events chat id: {config.events.chat_id}")
            setting.update_value(config.events.chat_id)
            session.commit()

        logger.debug(f"initializing EVENTS_CHAT filter ({setting.value()})...")
        ChatFilter.EVENTS.chat_ids = {setting.value()}

        staff_chat: Chat = chats.get_staff_chat(session)
        if staff_chat:
            logger.debug(f"initializing STAFF_CHAT filter ({staff_chat.chat_id})...")
            ChatFilter.STAFF.chat_ids = {staff_chat.chat_id}

        users_chat: Chat = chats.get_users_chat(session)
        if users_chat:
            logger.debug(f"initializing USERS_CHAT filter ({users_chat.chat_id})...")
            ChatFilter.USERS.chat_ids = {users_chat.chat_id}


init_filters()
