import datetime
import logging
from typing import List, Optional, Union, Tuple, Iterable

from sqlalchemy import Column, ForeignKey, Integer, Boolean, String, DateTime, Float, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from telegram import ChatMember, ChatMemberAdministrator, User as TelegramUser, Chat as TelegramChat, ChatMemberOwner, ChatMemberRestricted, \
    ChatMemberLeft, ChatMemberBanned, ChatMemberMember

import utilities
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
    stopped = Column(Boolean, default=False)
    stopped_on = Column(DateTime, default=None)

    # langauge
    language_code = Column(String, default=None)
    selected_language = Column(String, default=None)

    # ban
    banned = Column(Boolean, default=False)
    shadowban = Column(Boolean, default=False)
    banned_reason = Column(String, default=None)
    banned_on = Column(DateTime, default=None)

    # application (user)
    application_status = Column(Boolean, default=None)
    application_received_on = Column(DateTime, default=None)
    application_evaluated_on = Column(DateTime, default=None)
    application_evaluated_by_user_id = Column(Integer, default=None)

    # application (admin)
    can_evaluate_applications = Column(Boolean, default=False)

    last_message = Column(DateTime, default=None)  # to the staff's chat
    first_seen = Column(DateTime, default=utilities.now())  # private chat message/ChatMember update

    # relationships
    chat_members = relationship("ChatMember", back_populates="user")
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
        if self.user_id is None:
            # on record creation, this field is None
            self.user_id = telegram_user.id

        self.name = telegram_user.full_name
        self.first_name = telegram_user.first_name
        self.last_name = telegram_user.last_name
        self.username = telegram_user.username
        self.language_code = telegram_user.language_code
        self.is_bot = telegram_user.is_bot
        self.is_premium = telegram_user.is_premium

    def set_started(self):
        self.started = True
        if not self.started_on:
            self.started_on = utilities.now()

    def set_stopped(self):
        self.stopped = True
        self.stopped_on = utilities.now()

    def set_restarted(self):
        self.stopped = False
        self.stopped_on = None

    def update_last_message(self):
        self.last_message = utilities.now()

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
    username = Column(String, default=None)
    type = Column(String, default=None)
    is_forum = Column(Boolean, default=None)

    is_staff_chat = Column(Boolean, default=False)
    is_users_chat = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    left = Column(Boolean, default=None)
    first_seen = Column(DateTime, default=utilities.now())
    is_admin = Column(Boolean, default=False)  # whether the bot is admin or not
    can_delete_messages = Column(Boolean, default=False)  # whether the bot is allowed to delete messages or not
    last_administrators_fetch = Column(DateTime, default=None, nullable=True)

    chat_members = relationship("ChatMember", back_populates="chat", cascade="all, delete, delete-orphan, save-update")
    admin_messages = relationship("AdminMessage", back_populates="chat", cascade="all, delete, delete-orphan, save-update")

    def __init__(self, telegram_chat: TelegramChat):
        self.update_metadata(telegram_chat)

    def update_metadata(self, telegram_chat: TelegramChat):
        if self.chat_id is None:
            # on record creation, this field is None
            self.chat_id = telegram_chat.id

        self.title = telegram_chat.title
        self.username = telegram_chat.username
        self.type = telegram_chat.type
        self.is_forum = telegram_chat.is_forum

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


chat_member_union_type = Union[
    ChatMember,
    ChatMemberOwner,
    ChatMemberAdministrator,
    ChatMemberMember,
    ChatMemberRestricted,
    ChatMemberBanned,
    ChatMemberLeft
]


CHAT_MEMBER_DEFAULTS = dict(
    # ChatMemberAdministrator, ChatMemberOwner
    custom_title=None,
    is_anonymous=None,
    can_be_edited=False,
    # permissions
    can_manage_chat=False,
    can_delete_messages=False,
    can_manage_video_chats=False,
    can_restrict_members=False,
    can_promote_members=False,
    # these might depend on the chat's permisssions settings, so they default to None
    can_change_info=None,
    can_invite_users=None,
    can_pin_messages=None,
    can_manage_topics=None,
    # these are channels-only permissions
    can_post_messages=None,
    can_edit_messages=None,
    # ChatMemberRestricted, ChatMemberMember
    # None: defaults to the chat's permissions settings
    can_send_messages=None,
    can_send_audios=None,
    can_send_documents=None,
    can_send_photos=None,
    can_send_videos=None,
    can_send_video_notes=None,
    can_send_voice_notes=None,
    can_send_polls=None,
    can_send_other_messages=None,
    can_add_web_page_previews=None,
)


def chat_member_to_dict(chat_member: chat_member_union_type, chat_id: [None, int] = None) -> dict:
    is_owner = isinstance(chat_member, ChatMemberOwner)
    is_administrator = isinstance(chat_member, ChatMemberAdministrator) or is_owner
    is_member = isinstance(chat_member, ChatMemberMember)

    chat_member_dict = dict(
        user_id=chat_member.user.id,
        status=chat_member.status
    )

    # from pprint import pprint
    # pprint(chat_member.to_dict())
    for permission, default_value in CHAT_MEMBER_DEFAULTS.items():
        chat_member_dict[permission] = getattr(chat_member, permission, default_value)
        # logger.debug(f"<{chat_member.status}> permission <{permission}>: {chat_member_dict[permission]}")

    if chat_id:
        chat_member_dict["chat_id"] = chat_id

    return chat_member_dict


def chat_members_to_dict(chat_id: int, chat_members: Iterable[chat_member_union_type]):
    result = {}
    for chat_member in chat_members:
        # noinspection PyTypeChecker
        chat_member_dict = chat_member_to_dict(chat_member)
        chat_member_dict.update({"chat_id": chat_id})

        result[chat_member.user.id] = chat_member_dict

    return result


class ChatMember(Base):
    __tablename__ = 'chat_members'
    __allow_unmapped__ = True

    user_id = Column(Integer, ForeignKey('users.user_id'), primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.chat_id', ondelete="CASCADE"), primary_key=True)
    status = Column(String)

    # ChatMemberAdministrator, ChatMemberOwner
    is_anonymous = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["is_anonymous"])
    custom_title = Column(String, default=CHAT_MEMBER_DEFAULTS["custom_title"])
    can_be_edited = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_be_edited"])
    # permissions
    can_manage_chat = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_manage_chat"])
    can_delete_messages = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_delete_messages"])
    can_manage_video_chats = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_manage_video_chats"])
    can_restrict_members = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_restrict_members"])
    can_promote_members = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_promote_members"])
    can_change_info = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_change_info"])
    can_invite_users = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_invite_users"])
    can_post_messages = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_post_messages"])
    can_edit_messages = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_edit_messages"])
    can_pin_messages = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_pin_messages"])
    can_manage_topics = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_manage_topics"])

    # ChatMemberMember/ChatMemberRestricted
    # default to None: inherit the chat's default permissions
    can_send_messages = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_send_messages"])
    can_send_audios = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_send_audios"])
    can_send_documents = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_send_documents"])
    can_send_photos = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_send_photos"])
    can_send_videos = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_send_videos"])
    can_send_video_notes = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_send_video_notes"])
    can_send_voice_notes = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_send_voice_notes"])
    can_send_polls = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_send_polls"])
    can_send_other_messages = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_send_other_messages"])
    can_add_web_page_previews = Column(Boolean, default=CHAT_MEMBER_DEFAULTS["can_add_web_page_previews"])
    until_date = Column(DateTime, default=None)

    created_on = Column(DateTime, default=utilities.now())
    updated_on = Column(DateTime, default=utilities.now(), onupdate=utilities.now())

    user: User = relationship("User", back_populates="chat_members")
    chat: Chat = relationship("Chat", back_populates="chat_members")

    @classmethod
    def from_chat_member(cls, chat_id, chat_member: chat_member_union_type):
        chat_member_dict = chat_member_to_dict(chat_member)
        chat_member_dict.update({"chat_id": chat_id})
        # from pprint import pprint
        # pprint(chat_member_dict)

        return cls(**chat_member_dict)

    def is_administrator(self):
        return self.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)

    def is_member(self):
        return self.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER, ChatMember.RESTRICTED, ChatMember.MEMBER)

    def status_pretty(self):
        if self.status == ChatMember.OWNER:
            return "member (owner)"
        elif self.status == ChatMember.ADMINISTRATOR:
            return "member (admin)"
        elif self.status == ChatMember.MEMBER:
            return "member"
        elif self.status == ChatMember.RESTRICTED:
            return "member (restricted)"
        elif self.status == ChatMember.LEFT:
            return "not a member (never joined/left/removed but not banned)"
        elif self.status == ChatMember.BANNED:
            return "not a member (banned)"
        else:
            return self.status


class UserMessage(Base):
    __tablename__ = 'user_messages'
    __allow_unmapped__ = True

    message_id = Column(Integer, primary_key=True)  # we receive this just in private chats and it's incremental, so we can use it as primary key
    user_id = Column(Integer, ForeignKey('users.user_id'))
    forwarded_chat_id = Column(Integer, ForeignKey('chats.chat_id'))
    forwarded_message_id = Column(Integer)
    replies_count = Column(Integer, default=0)
    message_datetime = Column(DateTime, default=None)
    forwarded_on = Column(DateTime, default=utilities.now())
    updated_on = Column(DateTime, default=utilities.now(), onupdate=utilities.now())
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
        self.revoked_on = utilities.now()


class AdminMessage(Base):
    __tablename__ = 'admin_messages'
    __allow_unmapped__ = True

    message_id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.chat_id'), primary_key=True)
    user_message_id = Column(Integer, ForeignKey('user_messages.message_id'))
    user_id = Column(Integer, ForeignKey('users.user_id'))  # id of the admin
    reply_message_id = Column(Integer, nullable=False)  # forwarded reply sent to the user's private chat
    reply_datetime = Column(DateTime, default=utilities.now())
    message_datetime = Column(DateTime, default=None)
    updated_on = Column(DateTime, default=utilities.now(), onupdate=utilities.now())
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
        self.revoked_on = utilities.now()
        self.revoked_by = revoked_by


class LocalizedText(Base):
    __tablename__ = 'localized_texts'

    key = Column(String, primary_key=True)
    language = Column(String, primary_key=True, default=Language.EN)
    value = Column(String, default=None)
    updated_on = Column(DateTime, default=utilities.now(), onupdate=utilities.now())
    updated_by = Column(Integer, ForeignKey('users.user_id'))

    def __init__(self, key, language: str, value: Optional[str] = None, updated_by: Optional[int] = None):
        self.key = key.lower()
        self.language = language
        self.value = value
        self.updated_by = updated_by

    def save_updated_by(self, telegram_user: TelegramUser):
        self.updated_by = telegram_user.id
        self.updated_on = utilities.now()


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

    updated_on = Column(DateTime, default=utilities.now(), onupdate=utilities.now())
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

        self.updated_on = utilities.now()

    def update_null(self):
        self.value_type = None
        self.value_int = None
        self.value_bool = None
        self.value_str = None
        self.value_float = None
        self.value_date = None
        self.value_datetime = None

        self.updated_on = utilities.now()

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
    created_on = Column(DateTime, default=utilities.now())
    updated_on = Column(DateTime, default=utilities.now(), onupdate=utilities.now())
    updated_by = Column(Integer, ForeignKey('users.user_id'))

    def __init__(self, trigger: str, text: str, updated_by: int, language=Language.EN):
        self.trigger = trigger
        self.language = language
        self.trigger = trigger
        self.text = text
        self.updated_by = updated_by

