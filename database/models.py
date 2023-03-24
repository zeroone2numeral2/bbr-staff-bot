import datetime
from typing import List, Optional

from sqlalchemy import Column, ForeignKey, Integer, Boolean, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from telegram import ChatMember, ChatMemberAdministrator, User as TelegramUser

from .base import Base, engine


class User(Base):
    __tablename__ = 'users'

    user_id = Column(Integer, primary_key=True)
    name = Column(String, default=None)
    username = Column(String, default=None)
    started = Column(Boolean, default=False)  # we need to save every staff chat's admin, and they might have not started the bot yet
    language_code = Column(String, default=None)
    selected_language = Column(String, default=None)
    banned = Column(Boolean, default=False)
    banned_reason = Column(String, default=None)
    banned_on = Column(DateTime, default=None)

    started_on = Column(DateTime, default=None)
    last_message = Column(DateTime, default=None)

    chats_administrator = relationship("ChatAdministrator", back_populates="user")

    def __init__(
            self,
            user_id: int,
            name: Optional[str] = None,
            username: Optional[str] = None,
            language_code: Optional[str] = None,
            started: Optional[bool] = None
    ):
        self.user_id = user_id
        self.name = name
        self.username = username
        self.language_code = language_code
        if started is not None:
            self.started = started

    def update_metadata(self, telegram_user: TelegramUser):
        self.name = telegram_user.full_name
        self.username = telegram_user.username
        self.language_code = telegram_user.language_code

    def set_started(self, update_last_message=False):
        self.started = True
        if not self.started_on:
            self.started_on = func.now()
        if update_last_message:
            self.update_last_message()

    def update_last_message(self):
        self.last_message = func.now()

    def ban(self, reason: Optional[str] = None):
        self.banned = True
        self.banned_reason = reason
        self.banned_on = datetime.datetime.utcnow()

    def unban(self):
        self.banned = False
        self.banned_reason = None
        self.banned_on = None


class Chat(Base):
    __tablename__ = 'chats'

    chat_id = Column(Integer, primary_key=True)
    default = Column(Boolean, default=False)  # wether this is the current staff chat or not
    enabled = Column(Boolean, default=True)
    left = Column(Boolean, default=None)
    first_seen = Column(DateTime, server_default=func.now())
    last_administrators_fetch = Column(DateTime(timezone=True), default=None, nullable=True)

    chat_administrators = relationship("ChatAdministrator", back_populates="chat", cascade="all, delete, delete-orphan, save-update")
    settings = relationship("Setting", back_populates="chat", cascade="all, delete, delete-orphan, save-update")

    def __init__(self, chat_id):
        self.chat_id = chat_id

    def is_admin(self, user_id: int, permissions: [None, List], any_permission: bool = True, all_permissions: bool = False) -> bool:
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


def chat_member_to_dict(chat_member: ChatMemberAdministrator, chat_id: [None, int] = None) -> dict:
    is_owner = chat_member.status == ChatMember.OWNER

    chat_member_dict = dict(
        user_id=chat_member.user.id,
        status=chat_member.status,
        custom_title=chat_member.custom_title,
        is_anonymous=chat_member.is_anonymous,
        is_bot=chat_member.user.is_bot,
        can_manage_chat=chat_member.can_manage_chat or is_owner,
        can_delete_messages=chat_member.can_delete_messages or is_owner,
        can_manage_video_chats=chat_member.can_manage_video_chats or is_owner,
        can_restrict_members=chat_member.can_restrict_members or is_owner,
        can_promote_members=chat_member.can_promote_members or is_owner,
        can_change_info=chat_member.can_change_info or is_owner,
        can_invite_users=chat_member.can_invite_users or is_owner,
        can_post_messages=chat_member.can_post_messages or is_owner,
        can_edit_messages=chat_member.can_edit_messages or is_owner,
        can_pin_messages=chat_member.can_pin_messages or is_owner,
        can_manage_topics=chat_member.can_manage_topics or is_owner,
    )

    if chat_id:
        chat_member_dict["chat_id"] = chat_id

    return chat_member_dict


def chat_members_to_dict(chat_id: int, chat_members: List[ChatMemberAdministrator]):
    result = {}
    for chat_member in chat_members:
        chat_member_dict = chat_member_to_dict(chat_member)
        chat_member_dict.update({"chat_id": chat_id})

        result[chat_member.user.id] = chat_member_dict

    return result


class ChatAdministrator(Base):
    __tablename__ = 'chat_administrators'

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

    user = relationship("User", back_populates="chats_administrator")
    chat = relationship("Chat", back_populates="chat_administrators")

    @classmethod
    def from_chat_member(cls, chat_id, chat_member: ChatMemberAdministrator):
        chat_member_dict = chat_member_to_dict(chat_member)
        chat_member_dict.update({"chat_id": chat_id})

        return cls(**chat_member_dict)


class UserMessage(Base):
    __tablename__ = 'user_messages'

    message_id = Column(Integer, primary_key=True)  # we receive this just in private chats and it's incremental, so we can use it as primary key
    user_id = Column(Integer, ForeignKey('users.user_id'))
    forwarded_chat_id = Column(Integer, ForeignKey('chats.chat_id'))
    forwarded_message_id = Column(Integer)
    replies_count = Column(Integer, default=0)
    message_datetime = Column(DateTime, default=None)
    forwarded_on = Column(DateTime, server_default=func.now())
    updated_on = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __init__(self, message_id, user_id, forwarded_chat_id, forwarded_message_id, message_datetime):
        self.message_id = message_id
        self.user_id = user_id
        self.forwarded_chat_id = forwarded_chat_id
        self.forwarded_message_id = forwarded_message_id
        self.message_datetime = message_datetime

    def add_reply(self, count=1):
        self.replies_count = self.replies_count + count


class Setting(Base):
    __tablename__ = 'settings'

    chat_id = Column(Integer, ForeignKey('chats.chat_id'), primary_key=True)
    key = Column(String, primary_key=True)
    value = Column(String, default=None)
    updated_on = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey('users.user_id'))

    chat = relationship("Chat", back_populates="settings")
    user = relationship("User", back_populates="settings")

    def __init__(self, chat_id, key, value: Optional[str] = None):
        self.chat_id = chat_id
        self.key = key.lower()
        self.value = value

