import datetime
import logging
from typing import List, Optional, Union, Tuple

from sqlalchemy import Column, ForeignKey, Integer, Boolean, String, DateTime, Float, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from telegram import ChatMember, ChatMemberAdministrator, User as TelegramUser, ChatMemberOwner

from constants import Language
from .base import Base, engine

logger = logging.getLogger(__name__)


class User(Base):
    __tablename__ = 'users'

    user_id = Column(Integer, primary_key=True)
    name = Column(String, default=None)
    first_name = Column(String, default=None)
    last_name = Column(String, default=None)
    username = Column(String, default=None)
    is_bot = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)

    # started
    started = Column(Boolean, default=False)  # we need to save every staff chat's admin, and they might have not started the bot yet
    started_on = Column(DateTime, default=None)

    # langauge
    language_code = Column(String, default=None)
    selected_language = Column(String, default=None)

    # ban
    banned = Column(Boolean, default=False)
    shadowban = Column(Boolean, default=False)
    banned_reason = Column(String, default=None)
    banned_on = Column(DateTime, default=None)

    last_message = Column(DateTime, default=None)  # to the staff's chat
    first_seen = Column(DateTime, default=func.now())  # private chat message/ChatMember update

    # relationships
    chats_administrator = relationship("ChatAdministrator", back_populates="user")
    user_messages = relationship("UserMessage", back_populates="user")
    admin_messages = relationship("AdminMessage", back_populates="user")

    def __init__(self, telegram_user: TelegramUser, started: Optional[bool] = None):
        self.update_metadata(telegram_user)
        if started is not None:
            self.started = started

    def full_name(self):
        if not self.last_name:
            return self.first_name

        return f"{self.first_name} {self.last_name}"

    def update_metadata(self, telegram_user: TelegramUser):
        self.name = telegram_user.full_name
        self.first_name = telegram_user.first_name
        self.last_message = telegram_user.last_name
        self.username = telegram_user.username
        self.language_code = telegram_user.language_code
        self.is_bot = telegram_user.is_bot
        self.is_premium = telegram_user.is_premium

    def set_started(self):
        self.started = True
        if not self.started_on:
            self.started_on = func.now()

    def update_last_message(self):
        self.last_message = func.now()

    def ban(self, reason: Optional[str] = None, shadowban=False):
        self.banned = True
        self.shadowban = shadowban
        self.banned_reason = reason
        self.banned_on = datetime.datetime.utcnow()

    def unban(self):
        self.banned = False
        self.shadowban = False
        self.banned_reason = None
        self.banned_on = None


class Chat(Base):
    __tablename__ = 'chats'

    chat_id = Column(Integer, primary_key=True)
    title = Column(String, default=None)
    default = Column(Boolean, default=False)  # deprecated
    is_staff_chat = Column(Boolean, default=False)
    is_users_chat = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    left = Column(Boolean, default=None)
    first_seen = Column(DateTime, server_default=func.now())
    is_admin = Column(Boolean, default=False)  # whether the bot is admin or not
    can_delete_messages = Column(Boolean, default=False)  # whether the bot is allowed to delete messages or not
    last_administrators_fetch = Column(DateTime, default=None, nullable=True)

    chat_administrators = relationship("ChatAdministrator", back_populates="chat", cascade="all, delete, delete-orphan, save-update")
    admin_messages = relationship("AdminMessage", back_populates="chat", cascade="all, delete, delete-orphan, save-update")

    def __init__(self, chat_id, title):
        self.chat_id = chat_id
        self.title = title

    def is_staff_chat_backward(self):
        # for backward compatibility
        return self.default or self.is_staff_chat

    def is_user_admin(self, user_id: int, permissions: Optional[List] = None, any_permission: bool = True, all_permissions: bool = False) -> bool:
        if any_permission == all_permissions:
            raise ValueError("only one between any_permission and all_permissions can be True or False")

        for chat_administrator in self.chat_administrators:
            if chat_administrator.user_id != user_id:
                continue

            if not permissions:
                return True

            for permission in permissions:
                if getattr(chat_administrator, permission):
                    if any_permission:
                        return True
                else:
                    return False

            if all_permissions:
                return True
            else:
                return False

        return False

    def get_administrator(self, user_id):
        for administrator in self.chat_administrators:
            if administrator.user_id == user_id:
                return administrator

    def set_as_administrator(self, can_delete_messages: bool = None):
        self.is_admin = True
        if can_delete_messages is not None:
            self.can_delete_messages = can_delete_messages

    def unset_as_administrator(self):
        self.is_admin = False
        self.can_delete_messages = False

    def set_left(self):
        self.left = True
        self.unset_as_administrator()


def chat_member_to_dict(chat_member: ChatMemberAdministrator, chat_id: [None, int] = None) -> dict:
    is_owner = chat_member.status == ChatMember.OWNER

    chat_member_dict = dict(
        user_id=chat_member.user.id,
        status=chat_member.status,
        custom_title=chat_member.custom_title,
        is_anonymous=chat_member.is_anonymous,
        is_bot=chat_member.user.is_bot,
        can_manage_chat=True if is_owner else chat_member.can_manage_chat,
        can_delete_messages=True if is_owner else chat_member.can_delete_messages,
        can_manage_video_chats=True if is_owner else chat_member.can_manage_video_chats,
        can_restrict_members=True if is_owner else chat_member.can_restrict_members,
        can_promote_members=True if is_owner else chat_member.can_promote_members,
        can_change_info=True if is_owner else chat_member.can_change_info,
        can_invite_users=True if is_owner else chat_member.can_invite_users,
        can_post_messages=True if is_owner else chat_member.can_post_messages,
        can_edit_messages=True if is_owner else chat_member.can_edit_messages,
        can_pin_messages=True if is_owner else chat_member.can_pin_messages,
        can_manage_topics=True if is_owner else chat_member.can_manage_topics,
    )
    """ ChatMemberRestricted
    can_send_messages=True if is_owner else chat_member.can_send_messages,
    can_send_audios=True if is_owner else chat_member.can_send_audios,
    can_send_documents=True if is_owner else chat_member.can_send_documents,
    can_send_photos=True if is_owner else chat_member.can_send_photos,
    can_send_videos=True if is_owner else chat_member.can_send_videos,
    can_send_video_notes=True if is_owner else chat_member.can_send_video_notes,
    can_send_voice_notes=True if is_owner else chat_member.can_send_voice_notes,
    can_send_polls=True if is_owner else chat_member.can_send_polls,
    can_send_other_messages=True if is_owner else chat_member.can_send_other_messages,
    can_add_web_page_previews=True if is_owner else chat_member.can_add_web_page_previews,
    """

    if chat_id:
        chat_member_dict["chat_id"] = chat_id

    return chat_member_dict


def chat_members_to_dict(chat_id: int, chat_members: Tuple[ChatMember]):
    result = {}
    for chat_member in chat_members:
        # noinspection PyTypeChecker
        chat_member_dict = chat_member_to_dict(chat_member)
        chat_member_dict.update({"chat_id": chat_id})

        result[chat_member.user.id] = chat_member_dict

    return result


class ChatAdministrator(Base):
    __tablename__ = 'chat_administrators'
    __allow_unmapped__ = True

    user_id = Column(Integer, ForeignKey('users.user_id'), primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.chat_id', ondelete="CASCADE"), primary_key=True)
    status = Column(String)
    custom_title = Column(String, default=None)
    is_anonymous = Column(Boolean, default=False)
    is_bot = Column(Boolean, default=False)
    can_manage_chat = Column(Boolean, default=True)
    can_delete_messages = Column(Boolean, default=False)
    can_manage_video_chats = Column(Boolean, default=False)
    can_restrict_members = Column(Boolean, default=False)
    can_promote_members = Column(Boolean, default=False)
    can_change_info = Column(Boolean, default=False)
    can_invite_users = Column(Boolean, default=False)
    can_post_messages = Column(Boolean, default=False)
    can_edit_messages = Column(Boolean, default=False)
    can_pin_messages = Column(Boolean, default=False)
    can_manage_topics = Column(Boolean, default=False)

    updated_on = Column(DateTime, server_default=func.now(), onupdate=func.now())
    # updated_on = Column(DateTime(timezone=True), onupdate=func.now())  # https://stackoverflow.com/a/33532154

    user: User = relationship("User", back_populates="chats_administrator")
    chat: Chat = relationship("Chat", back_populates="chat_administrators")

    @classmethod
    def from_chat_member(cls, chat_id, chat_member: ChatMemberAdministrator):
        chat_member_dict = chat_member_to_dict(chat_member)
        chat_member_dict.update({"chat_id": chat_id})

        return cls(**chat_member_dict)


"""
class ChatMember(Base):
    __tablename__ = 'chat_members'
    __allow_unmapped__ = True

    user_id = Column(Integer, ForeignKey('users.user_id'), primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.chat_id', ondelete="CASCADE"), primary_key=True)
    status = Column(String)
    is_anonymous = Column(Boolean, default=False)
    custom_title = Column(String, default=None)

    # ChatMemberAdministrator
    can_be_edited = Column(Boolean, default=False)
    can_manage_chat = Column(Boolean, default=True)
    can_delete_messages = Column(Boolean, default=False)
    can_manage_video_chats = Column(Boolean, default=False)
    can_restrict_members = Column(Boolean, default=False)
    can_promote_members = Column(Boolean, default=False)
    can_change_info = Column(Boolean, default=False)
    can_invite_users = Column(Boolean, default=False)
    can_post_messages = Column(Boolean, default=False)
    can_edit_messages = Column(Boolean, default=False)
    can_pin_messages = Column(Boolean, default=False)
    can_manage_topics = Column(Boolean, default=False)

    # ChatMemberRestricted
    can_send_messages = Column(Boolean, default=False)
    can_send_audios = Column(Boolean, default=False)
    can_send_documents = Column(Boolean, default=False)
    can_send_photos = Column(Boolean, default=False)
    can_send_videos = Column(Boolean, default=False)
    can_send_video_notes = Column(Boolean, default=False)
    can_send_voice_notes = Column(Boolean, default=False)
    can_send_polls = Column(Boolean, default=False)
    can_send_other_messages = Column(Boolean, default=False)
    can_add_web_page_previews = Column(Boolean, default=False)
    until_date = Column(DateTime, default=None)

    updated_on = Column(DateTime, default=func.now(), onupdate=func.now())

    # user: User = relationship("User", back_populates="chats_administrator")
    # chat: Chat = relationship("Chat", back_populates="chat_administrators")

    @classmethod
    def from_chat_member(cls, chat_id, chat_member: ChatMemberAdministrator):
        chat_member_dict = chat_member_to_dict(chat_member)
        chat_member_dict.update({"chat_id": chat_id})

        return cls(**chat_member_dict)
"""


class UserMessage(Base):
    __tablename__ = 'user_messages'
    __allow_unmapped__ = True

    message_id = Column(Integer, primary_key=True)  # we receive this just in private chats and it's incremental, so we can use it as primary key
    user_id = Column(Integer, ForeignKey('users.user_id'))
    forwarded_chat_id = Column(Integer, ForeignKey('chats.chat_id'))
    forwarded_message_id = Column(Integer)
    replies_count = Column(Integer, default=0)
    message_datetime = Column(DateTime, default=None)
    forwarded_on = Column(DateTime, server_default=func.now())
    updated_on = Column(DateTime, server_default=func.now(), onupdate=func.now())
    revoked = Column(Boolean, default=False)
    revoked_on = Column(DateTime, default=None)
    message_json = Column(String, default=None)

    user: User = relationship("User", back_populates="user_messages")
    admin_messages = relationship("AdminMessage", back_populates="user_message")

    def __init__(self, message_id, user_id, forwarded_chat_id, forwarded_message_id, message_datetime):
        self.message_id = message_id
        self.user_id = user_id
        self.forwarded_chat_id = forwarded_chat_id
        self.forwarded_message_id = forwarded_message_id
        self.message_datetime = message_datetime

    def add_reply(self, count=1):
        if self.replies_count is None:
            self.replies_count = 0
        self.replies_count += count

    def revoke(self):
        self.revoked = True
        self.revoked_on = func.now()


class AdminMessage(Base):
    __tablename__ = 'admin_messages'
    __allow_unmapped__ = True

    message_id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.chat_id'), primary_key=True)
    user_message_id = Column(Integer, ForeignKey('user_messages.message_id'))
    user_id = Column(Integer, ForeignKey('users.user_id'))  # id of the admin
    reply_message_id = Column(Integer, nullable=False)  # forwarded reply sent to the user's private chat
    reply_datetime = Column(DateTime, server_default=func.now())
    message_datetime = Column(DateTime, default=None)
    updated_on = Column(DateTime, server_default=func.now(), onupdate=func.now())
    revoked = Column(Boolean, default=False)
    revoked_on = Column(DateTime, default=None)
    revoked_by = Column(Integer, nullable=True)
    message_json = Column(String, default=None)

    chat: Chat = relationship("Chat", back_populates="admin_messages")
    user: User = relationship("User", back_populates="admin_messages")
    user_message: UserMessage = relationship("UserMessage", back_populates="admin_messages")

    def __init__(self, message_id, chat_id, user_id, user_message_id, reply_message_id, message_datetime):
        self.message_id = message_id
        self.chat_id = chat_id
        self.user_id = user_id
        self.user_message_id = user_message_id
        self.reply_message_id = reply_message_id
        self.message_datetime = message_datetime

    def revoke(self, revoked_by: Optional[int] = None):
        self.revoked = True
        self.revoked_on = func.now()
        self.revoked_by = revoked_by


class LocalizedText(Base):
    __tablename__ = 'localized_texts'

    key = Column(String, primary_key=True)
    language = Column(String, primary_key=True, default=Language.EN)
    value = Column(String, default=None)
    updated_on = Column(DateTime, default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey('users.user_id'))

    def __init__(self, key, language: str, value: Optional[str] = None, updated_by: Optional[int] = None):
        self.key = key.lower()
        self.language = language
        self.value = value
        self.updated_by = updated_by


class ValueType:
    BOOL = "bool"
    INT = "int"
    STR = "str"
    FLOAT = "float"
    DATETIME = "datetime"
    DATE = "date"


class BotSetting(Base):
    __tablename__ = 'bot_settings'

    key = Column(String, primary_key=True)

    value_bool = Column(Boolean, default=None)
    value_int = Column(Integer, default=None)
    value_float = Column(Float, default=None)
    value_str = Column(String, default=None)
    value_datetime = Column(DateTime, default=None)
    value_date = Column(Date, default=None)

    value_type = Column(String, default=None)

    updated_on = Column(DateTime, default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey('users.user_id'))

    def __init__(self, key, value=None):
        self.key = key.lower()
        self.update_value(value, raise_on_unknown_type=True)

    def update_value(self, value, raise_on_unknown_type=True):
        # auto-detect the setting type
        if isinstance(value, bool):
            self.value_bool = value
            self.value_type = ValueType.BOOL
        elif isinstance(value, int):
            self.value_int = value
            self.value_type = ValueType.INT
        elif isinstance(value, float):
            self.value_float = value
            self.value_type = ValueType.FLOAT
        elif isinstance(value, str):
            self.value_str = value
            self.value_type = ValueType.STR
        elif isinstance(value, datetime.datetime):
            self.value_datetime = value
            self.value_type = ValueType.DATETIME
        elif isinstance(value, datetime.date):
            self.value_date = value
            self.value_type = ValueType.DATE
        else:
            if raise_on_unknown_type:
                raise ValueError(f"provided value of unrecognized type: {type(value)}")

    def update_null(self):
        self.value_type = None
        self.value_int = None
        self.value_bool = None
        self.value_str = None
        self.value_float = None
        self.value_date = None
        self.value_datetime = None

    def value(self):
        if self.value_type == ValueType.BOOL:
            return self.value_bool
        elif self.value_type == ValueType.INT:
            return self.value_int
        elif self.value_type == ValueType.FLOAT:
            return self.value_float
        elif self.value_type == ValueType.STR:
            return self.value_str
        elif self.value_type == ValueType.DATETIME:
            return self.value_datetime
        elif self.value_type == ValueType.DATE:
            return self.value_date

    def value_pretty(self):
        raw_value = self.value()
        if self.value_type == ValueType.BOOL:
            return str(raw_value).lower()
        elif raw_value is None:
            return "null"
        else:
            return raw_value

    def __repr__(self):
        return f"BotSetting(key=\"{self.key}\", value_type=\"{self.value_type}\", value={self.value()})"


class CustomCommand(Base):
    __tablename__ = 'custom_commands'

    trigger = Column(String, primary_key=True)
    language = Column(String, primary_key=True, default=Language.EN)
    text = Column(String, default=None)
    enabled_text = Column(Boolean, default=True)
    enabled_inline = Column(Boolean, default=True)
    created_on = Column(DateTime, server_default=func.now())
    updated_on = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey('users.user_id'))

    def __init__(self, trigger: str, text: str, updated_by: int, language=Language.EN):
        self.trigger = trigger
        self.language = language
        self.trigger = trigger
        self.text = text
        self.updated_by = updated_by

