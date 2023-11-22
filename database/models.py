import datetime
import json
import logging
from typing import List, Optional, Union, Iterable

from sqlalchemy import Column, ForeignKey, Integer, Boolean, String, DateTime, Float, Date, Index
from sqlalchemy.orm import relationship, mapped_column, Mapped
from telegram import ChatMember as TgChatMember, ChatMemberAdministrator, User as TelegramUser, Chat as TelegramChat, \
    ChatMemberOwner, ChatMemberRestricted, \
    ChatMemberLeft, ChatMemberBanned, ChatMemberMember, Message, InputMediaPhoto, InputMediaVideo, ChatInviteLink
from telegram.helpers import mention_html

import utilities
from config import config
from constants import Language
from emojis import Emoji
from .base import Base

logger = logging.getLogger(__name__)


class User(Base):
    __tablename__ = 'users'

    # metadata
    user_id = mapped_column(Integer, primary_key=True)
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

    # radar
    can_use_radar = Column(Boolean, default=False)  # applies only if settings.radar_password is set

    # langauge
    language_code = Column(String, default=None)
    selected_language = Column(String, default=None)

    # ban
    banned = Column(Boolean, default=False)
    shadowban = Column(Boolean, default=False)
    banned_reason = Column(String, default=None)
    banned_on = Column(DateTime, default=None)

    # application (user)
    pending_request_id = mapped_column(Integer, default=None)  # pending ApplicationRequest (pending: not yet accepted/rejected, waiting for evaluation)
    last_request_id = mapped_column(Integer, default=None)  # last request accepted/rejected by the admins
    conversate_with_staff_override = Column(Boolean, default=False)  # whether the user can conversate with the staff even when a request is pending/rejected

    # application (admin)
    can_evaluate_applications = Column(Boolean, default=False)

    # invited by
    invited_by_user_id = mapped_column(Integer, default=None)
    invited_on = Column(DateTime, default=None)

    last_message = Column(DateTime, default=None)  # to the staff's chat
    first_seen = Column(DateTime, default=utilities.now)  # private chat message/ChatMember update

    # relationships
    chat_members = relationship("ChatMember", back_populates="user")
    user_messages = relationship("UserMessage", back_populates="user")
    admin_messages = relationship("AdminMessage", back_populates="staff_user")
    private_chat_messages = relationship("PrivateChatMessage", back_populates="user")
    # application_requests = relationship("ApplicationRequest", back_populates="user")

    # no foreign key for columns added after the table creation (https://stackoverflow.com/q/30378233),
    # we need to specify the 'primaryjoin' condition
    invited_by: Mapped['User'] = relationship(
        "User",
        foreign_keys=invited_by_user_id,
        primaryjoin="User.user_id == User.invited_by_user_id",
        remote_side=user_id,
        uselist=False
    )
    pending_request: Mapped['ApplicationRequest'] = relationship(
        "ApplicationRequest",
        foreign_keys=pending_request_id,
        primaryjoin="User.pending_request_id == ApplicationRequest.id",
        # remote_side=user_id,  # breaks the relationship for some reason
        uselist=False
    )
    last_request: Mapped['ApplicationRequest'] = relationship(
        "ApplicationRequest",
        foreign_keys=last_request_id,
        primaryjoin="User.last_request_id == ApplicationRequest.id",
        # remote_side=user_id,  # breaks the relationship for some reason
        uselist=False
    )
    users_chat_member: Mapped['ChatMember'] = relationship(
        "ChatMember",
        foreign_keys=user_id,
        primaryjoin="and_(User.user_id == ChatMember.user_id, ChatMember.chat_id == select(Chat.chat_id).filter(Chat.is_users_chat == true()))",
        # remote_side=user_id,
        uselist=False,
        lazy="select"  # https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html
    )

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

    def mention(self, full_name=True, escape=True):
        name = self.full_name() if full_name else self.first_name
        if escape:
            name = utilities.escape_html(name)

        return mention_html(self.user_id, name)

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

    def accept(self, by_user_id: int, notes: Optional[str] = None):
        self.pending_request.accept(by_user_id, notes)
        self.last_request_id = self.pending_request_id
        self.pending_request_id = None

        # no need to have this set to True once the user is accepted
        self.conversate_with_staff_override = False

    def reject(self, by_user_id: int, notes: Optional[str] = None):
        self.pending_request.reject(by_user_id, notes)
        self.last_request_id = self.pending_request_id
        self.pending_request_id = None

        # we set this to false also when the user is rejected
        self.conversate_with_staff_override = False

    def reset_evaluation(self, keep_pending=False):
        if not keep_pending:
            self.pending_request_id = None
        self.last_request_id = None
        self.conversate_with_staff_override = False


class ChatDestination:
    STAFF = "staff"
    USERS = "users"
    EVALUATION = "evaluation"
    LOG = "log"
    EVENTS = "venets"


class Chat(Base):
    __tablename__ = 'chats'

    DESTINATION_TYPES_GROUP = (ChatDestination.STAFF, ChatDestination.USERS, ChatDestination.EVALUATION)
    DESTINATION_TYPES_CHANNEL = (ChatDestination.LOG, ChatDestination.EVENTS)

    chat_id = Column(Integer, primary_key=True)
    title = Column(String, default=None)
    username = Column(String, default=None)
    type = Column(String, default=None)
    is_forum = Column(Boolean, default=None)

    is_staff_chat = Column(Boolean, default=False)
    is_evaluation_chat = Column(Boolean, default=False)
    is_users_chat = Column(Boolean, default=False)
    is_events_chat = Column(Boolean, default=False)
    is_log_chat = Column(Boolean, default=False)
    is_modlog_chat = Column(Boolean, default=False)

    enabled = Column(Boolean, default=True)
    left = Column(Boolean, default=None)
    first_seen = Column(DateTime, default=utilities.now)
    is_admin = Column(Boolean, default=False)  # whether the bot is admin or not
    can_delete_messages = Column(Boolean, default=False)  # whether the bot is allowed to delete messages or not
    can_invite_users = Column(Boolean, default=False)  # whether the bot can manage invite links
    last_administrators_fetch = Column(DateTime, default=None, nullable=True)
    save_chat_members = Column(Boolean, default=False)  # wether to save chat member updates even if the chat is not `special`

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

    def title_escaped(self):
        return utilities.escape_html(self.title)

    def type_pretty(self):
        if self.is_staff_chat:
            return "staff chat"
        if self.is_users_chat:
            return "users chat"
        if self.is_events_chat:
            return "events chat"
        if self.is_log_chat:
            return "log chat"
        if self.is_evaluation_chat:
            return "evaluation chat"
        else:
            return "chat"

    def type_pretty_it(self):
        if self.is_staff_chat:
            return "chat staff"
        if self.is_users_chat:
            return "chat utenti"
        if self.is_events_chat:
            return "chat eventi"
        if self.is_log_chat:
            return "chat log"
        if self.is_evaluation_chat:
            return "chat approvazioni"
        else:
            return "chat"

    def set_as_administrator(self, can_delete_messages: bool = None, can_invite_users: bool = None):
        self.is_admin = True
        if can_delete_messages is not None:
            self.can_delete_messages = can_delete_messages
        if can_invite_users is not None:
            self.can_invite_users = can_invite_users

    def unset_as_administrator(self):
        self.is_admin = False
        self.can_delete_messages = False
        self.can_invite_users = False

    def set_left(self):
        self.left = True
        self.unset_as_administrator()

    def set_as_staff_chat(self):
        self.is_staff_chat = True
        self.is_evaluation_chat = False
        self.is_users_chat = False

    def set_as_users_chat(self):
        self.is_users_chat = True
        self.is_evaluation_chat = False
        self.is_staff_chat = False

    def set_as_evaluation_chat(self):
        self.is_evaluation_chat = True
        self.is_users_chat = False
        self.is_staff_chat = False

    def set_as_log_chat(self):
        self.is_log_chat = True
        self.is_events_chat = False

    def set_as_events_chat(self):
        self.is_events_chat = True
        self.is_log_chat = False

    def is_special_chat(self):
        return self.is_users_chat or self.is_staff_chat or self.is_evaluation_chat or self.is_events_chat or self.is_log_chat


chat_member_union_type = Union[
    TgChatMember,
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
    MEMBER_STATUSES = (TgChatMember.ADMINISTRATOR, TgChatMember.OWNER, TgChatMember.RESTRICTED, TgChatMember.MEMBER)
    ADMINISTRATOR_STATUSES = (TgChatMember.ADMINISTRATOR, TgChatMember.OWNER)

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

    # flag set only when the user has been seen in the group
    # there might be BANNED and RESTRICTED users that have never been part of the chat
    has_been_member = Column(Boolean, default=False)
    kicked = Column(Boolean, default=False)

    created_on = Column(DateTime, default=utilities.now)
    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)

    user: User = relationship("User", back_populates="chat_members")
    chat: Chat = relationship("Chat", back_populates="chat_members")

    @classmethod
    def from_chat_member(cls, chat_id, chat_member: chat_member_union_type):
        chat_member_dict = chat_member_to_dict(chat_member)
        chat_member_dict.update({"chat_id": chat_id})
        if chat_member.status in cls.MEMBER_STATUSES:
            chat_member_dict.update({"has_been_member": True})

        # from pprint import pprint
        # pprint(chat_member_dict)

        return cls(**chat_member_dict)

    def is_administrator(self):
        return self.status in self.ADMINISTRATOR_STATUSES

    def is_member(self):
        return self.status in self.MEMBER_STATUSES

    def is_banned(self):
        return self.status == TgChatMember.BANNED

    def left_or_kicked(self):
        # the user has been member, but they:
        # - left the chat
        # - were removed but are no longer in the blocked users list (can join again)
        return self.status == TgChatMember.LEFT and self.has_been_member

    def update_has_been_member(self):
        if self.is_member():
            # do not set this flag if banned: there might be banned users that never joined
            self.has_been_member = True

    def status_pretty(self):
        if self.status == TgChatMember.OWNER:
            return "member (owner)"
        elif self.status == TgChatMember.ADMINISTRATOR:
            return "member (admin)"
        elif self.status == TgChatMember.MEMBER:
            return "member"
        elif self.status == TgChatMember.RESTRICTED:
            return "member (restricted)"
        elif self.status == TgChatMember.LEFT:
            return "not a member (never joined/left/removed but not banned)"
        elif self.status == TgChatMember.BANNED:
            return "not a member (banned)"
        else:
            return self.status

    def __repr__(self):
        return f"ChatMember(user_id={self.chat_id}, chat_id={self.user_id}, status=\"{self.status}\")"


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
    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)
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

    def save_message_json(self, message: Message):
        if not config.settings.db_save_json:
            return

        # we convert manually because Message.to_json() doesn't indent
        self.message_json = json.dumps(message.to_dict(), indent=2)


class AdminMessage(Base):
    __tablename__ = 'admin_messages'
    __allow_unmapped__ = True

    message_id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.chat_id'), primary_key=True)  # id of the admins chat
    staff_user_id = Column(Integer, ForeignKey('users.user_id'))  # id of the staff user that replied
    target_user_id = mapped_column(Integer, nullable=False)  # id of the user the staff is interacting with
    user_message_id = Column(Integer, ForeignKey('user_messages.message_id'))  # id of the UserMessage
    reply_message_id = Column(Integer, nullable=False)  # forwarded reply sent to the user's private chat
    reply_datetime = Column(DateTime, default=utilities.now())
    message_datetime = Column(DateTime, default=None)
    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)
    revoked = Column(Boolean, default=False)
    revoked_on = Column(DateTime, default=None)
    revoked_by = Column(Integer, nullable=True)
    message_json = Column(String, default=None)

    chat: Chat = relationship("Chat", back_populates="admin_messages")
    staff_user: User = relationship("User", back_populates="admin_messages")
    user_message: UserMessage = relationship("UserMessage", back_populates="admin_messages")

    target_user: Mapped['User'] = relationship(
        "User",
        foreign_keys=target_user_id,
        primaryjoin="User.user_id == AdminMessage.target_user_id",
        # remote_side=user_id,
        uselist=False
    )

    def __init__(self, message_id, chat_id, staff_user_id, target_user_id, user_message_id, reply_message_id, message_datetime):
        self.message_id = message_id
        self.chat_id = chat_id
        self.staff_user_id = staff_user_id
        self.target_user_id = target_user_id
        self.user_message_id = user_message_id
        self.reply_message_id = reply_message_id
        self.message_datetime = message_datetime

    def revoke(self, revoked_by: Optional[int] = None):
        self.revoked = True
        self.revoked_on = utilities.now()
        self.revoked_by = revoked_by

    def save_message_json(self, message: Message):
        if not config.settings.db_save_json:
            return

        self.message_json = json.dumps(message.to_dict(), indent=2)


class LocalizedText(Base):
    __tablename__ = 'localized_texts'

    key = Column(String, primary_key=True)
    language = Column(String, primary_key=True, default=Language.EN)
    value = Column(String, default=None)

    show_if_true_bot_setting_key = mapped_column(String, default=None)  # only show this setting if the parent setting is true

    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)
    updated_by = Column(Integer, ForeignKey('users.user_id'))

    show_if_true = relationship(
        "BotSetting",
        foreign_keys=show_if_true_bot_setting_key,
        primaryjoin="LocalizedText.show_if_true_bot_setting_key == BotSetting.key",
        remote_side="BotSetting.key",  # very important!!!
        uselist=False
    )

    def __init__(self, key, language: str, value: Optional[str] = None, updated_by: Optional[int] = None, show_if_true_bot_setting_key: Optional[str] = None):
        self.key = key.lower()
        self.language = language
        self.value = value
        self.updated_by = updated_by
        self.show_if_true_bot_setting_key = show_if_true_bot_setting_key

    def save_updated_by(self, telegram_user: TelegramUser):
        self.updated_by = telegram_user.id
        self.updated_on = utilities.now()

    def show(self):
        if not self.show_if_true:
            return True
        return self.show_if_true.value_bool


class ValueType:
    BOOL = "bool"
    INT = "int"
    STR = "str"
    FLOAT = "float"
    DATETIME = "datetime"
    DATE = "date"
    MEDIA = "media"


class BotSetting(Base):
    __tablename__ = 'bot_settings'

    key = Column(String, primary_key=True)
    category = Column(String, default=None)

    value_bool = Column(Boolean, default=None)
    value_int = Column(Integer, default=None)
    value_float = Column(Float, default=None)
    value_str = Column(String, default=None)
    value_datetime = Column(DateTime, default=None)
    value_date = Column(Date, default=None)

    # telegram medias
    value_media_file_id = Column(String, default=None)
    value_media_file_unique_id = Column(String, default=None)
    value_media_type = Column(String, default=None)

    value_type = Column(String, default=None)

    show_if_true_key = mapped_column(String, default=None)  # only show this setting if the parent setting is true

    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)
    updated_by = Column(Integer, ForeignKey('users.user_id'))

    # figure out from this: https://docs.sqlalchemy.org/en/20/orm/join_conditions.html#creating-custom-foreign-conditions
    show_if_true = relationship(
        "BotSetting",
        foreign_keys=show_if_true_key,
        primaryjoin="BotSetting.show_if_true_key == BotSetting.key",
        remote_side=key,  # very important!!!
        uselist=False
    )

    def __init__(self, key: str, category: str, value=None, telegram_media=False, show_if_true_key=None):
        self.key = key
        self.category = category
        self.update_value(value, telegram_media=telegram_media, raise_on_unknown_type=False)
        self.show_if_true_key = show_if_true_key

    def update_value(self, value, telegram_media=False, raise_on_unknown_type=True):
        self.update_null()

        # auto-detect the setting type
        if telegram_media:
            self.value_media_file_id = value
            self.value_type = ValueType.MEDIA
        elif isinstance(value, bool):
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

    def update_value_telegram_media(self, file_id: str, file_unique_id: str, media_type: str):
        self.update_null()

        self.value_type = ValueType.MEDIA

        self.value_media_file_id = file_id
        self.value_media_file_unique_id = file_unique_id
        self.value_media_type = media_type

    def update_null(self):
        # self.value_type = None  # do not nullify this: if it was a media setting, it must stay a media setting
        self.value_int = None
        self.value_bool = None
        self.value_str = None
        self.value_float = None
        self.value_date = None
        self.value_datetime = None

        self.value_media_type = None
        self.value_media_file_id = None
        self.value_media_file_unique_id = None

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
        elif self.value_type == ValueType.MEDIA:
            return self.value_media_file_id

    def value_pretty(self):
        raw_value = self.value()
        if self.value_type == ValueType.MEDIA:
            return f"{self.value_media_type if self.value_media_type else 'null'}"
        elif self.value_type == ValueType.BOOL:
            return str(raw_value).lower()
        elif raw_value is None:
            return "null"
        else:
            return raw_value

    def show(self):
        if not self.show_if_true:
            return True
        return self.show_if_true.value_bool

    def __repr__(self):
        return f"BotSetting(key=\"{self.key}\", value_type=\"{self.value_type}\", value={self.value()})"


class CustomCommand(Base):
    __tablename__ = 'custom_commands'

    trigger = Column(String, primary_key=True)
    language = Column(String, primary_key=True, default=Language.EN)
    text = Column(String, default=None)
    enabled_text = Column(Boolean, default=True)
    enabled_inline = Column(Boolean, default=True)
    created_on = Column(DateTime, default=utilities.now)
    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)
    updated_by = Column(Integer, ForeignKey('users.user_id'))

    def __init__(self, trigger: str, text: str, updated_by: int, language=Language.EN):
        self.trigger = trigger
        self.language = language
        self.trigger = trigger
        self.text = text
        self.updated_by = updated_by


class PrivateChatMessage(Base):
    __tablename__ = 'private_chat_messages'
    __allow_unmapped__ = True

    message_id = Column(Integer, primary_key=True)  # we receive this just in private chats and it's incremental, so we can use it as primary key
    user_id = Column(Integer, ForeignKey('users.user_id'))
    from_self = Column(Boolean, default=False)
    date = Column(DateTime, default=None)
    saved_on = Column(DateTime, default=utilities.now)
    revoked = Column(Boolean, default=False)
    revoked_on = Column(DateTime, default=None)
    revoked_reason = Column(String, default=None)
    message_json = Column(String, default=None)

    user: User = relationship("User", back_populates="private_chat_messages")

    def __init__(
            self,
            message_id: int,
            user_id: int,
            from_self: Optional[bool] = False,
            date: Optional[datetime.datetime] = None,
            message_json: Optional[str] = None
    ):
        self.message_id = message_id
        self.user_id = user_id
        self.from_self = from_self
        self.date = date
        if config.settings.db_save_json:
            self.message_json = message_json

    def set_revoked(self, reason=None):
        self.revoked = True
        self.revoked_on = utilities.now()
        self.revoked_reason = reason

    def can_be_deleted(self, now_dt: Optional[datetime.datetime] = None) -> bool:
        if not now_dt:
            now_dt = utilities.now()

        timedelta_48_hours_ago = datetime.timedelta(hours=48)

        if self.date:
            return utilities.naive_to_aware(self.date, force_utc=True) > (now_dt - timedelta_48_hours_ago)
        elif self.saved_on:
            return utilities.naive_to_aware(self.saved_on, force_utc=True) > (now_dt - timedelta_48_hours_ago)

        return False


# https://t.me/c/1289562489/569
class EventTypeHashtag:
    FREE = "#freeparty"
    TEKNIVAL = "#teknival"
    LEGAL = "#legal"
    LEGAL_PARTY = "#legalparty"
    LEGAL_PLACE = "#legalplace"
    LOCALATA = "#localata"
    CS = "#cs"
    CSO = "#cso"
    CSOA = "#csoa"
    CSOA_PARTY = "#csoaparty"
    SQUAT_PARTY = "#squatparty"
    SQUAT = "#squat"
    TAZ = "#taz"
    MANIFESTAZIONE = "#manifestazione"
    CORTEO = "#corteo"
    STREET_PARADE = "#streetparade"
    PRIVATE_PARTY = "#privateparty"
    FESTIVAL = "#festival"


class EventType:
    # value saved in the db
    FREE = "free"
    LEGAL = "legal"
    PRIVATE = "private"
    CS_OR_SQUAT = "cs_or_squat"
    STREET_PARADE = "street_parade"
    OTHER = "other"


EVENT_TYPE = {
    # if a message has more the one hashtag in this dict, the first one will be used
    EventTypeHashtag.FREE: EventType.FREE,
    EventTypeHashtag.TEKNIVAL: EventType.FREE,
    EventTypeHashtag.LEGAL: EventType.LEGAL,
    EventTypeHashtag.LEGAL_PARTY: EventType.LEGAL,
    EventTypeHashtag.LEGAL_PLACE: EventType.LEGAL,
    EventTypeHashtag.LOCALATA: EventType.LEGAL,
    EventTypeHashtag.FESTIVAL: EventType.LEGAL,
    EventTypeHashtag.CS: EventType.CS_OR_SQUAT,
    EventTypeHashtag.CSO: EventType.CS_OR_SQUAT,
    EventTypeHashtag.CSOA: EventType.CS_OR_SQUAT,
    EventTypeHashtag.CSOA_PARTY: EventType.CS_OR_SQUAT,
    EventTypeHashtag.SQUAT: EventType.CS_OR_SQUAT,
    EventTypeHashtag.SQUAT_PARTY: EventType.CS_OR_SQUAT,
    EventTypeHashtag.TAZ: EventType.CS_OR_SQUAT,
    EventTypeHashtag.PRIVATE_PARTY: EventType.PRIVATE,
    EventTypeHashtag.STREET_PARADE: EventType.STREET_PARADE,
    EventTypeHashtag.MANIFESTAZIONE: EventType.OTHER,
    EventTypeHashtag.CORTEO: EventType.OTHER,
}


class DeletionReason:
    DUPLICATE = 10
    MESSAGE_DELETED = 20
    NOT_A_PARTY = 30
    OTHER = 100


DELETION_REASON_DESC = {
    DeletionReason.DUPLICATE: "duplicato",
    DeletionReason.MESSAGE_DELETED: "il messaggio è stato eliminato",
    DeletionReason.NOT_A_PARTY: "il messaggio non riguadrava una festa",
    DeletionReason.OTHER: "altro"
}


class Event(Base):
    __tablename__ = 'events'
    __allow_unmapped__ = True

    chat_id = Column(Integer, ForeignKey('chats.chat_id'), primary_key=True)
    message_id = Column(Integer, primary_key=True)

    # info about the channel post that was forwarded to the discussion group
    discussion_group_chat_id = Column(Integer, default=None)
    discussion_group_message_id = Column(Integer, default=None)
    discussion_group_received_on = Column(DateTime, default=None)
    discussion_group_message_json = Column(String, default=None)

    event_id = Column(Integer, default=None)
    event_title = Column(String, default=None)

    start_date = Column(Date, default=None)  # just a convenience Date column that should be used for queries
    start_week = Column(Integer, default=None)  # also a convenience column that should be used for queries
    start_day = Column(Integer, default=None)
    start_month = Column(Integer, default=None)
    start_year = Column(Integer, default=None)

    end_date = Column(Date, default=None)  # just a convenience Date column that should be used for queries
    end_day = Column(Integer, default=None)
    end_month = Column(Integer, default=None)
    end_year = Column(Integer, default=None)

    soon = Column(Boolean, default=False)
    region = Column(String, default=None)
    event_type = Column(String, default=None)
    canceled = Column(Boolean, default=False)
    parsing_errors = Column(String, default=None)

    message_text = Column(String, default=None)
    message_date = Column(DateTime, default=None)
    message_edit_date = Column(DateTime, default=None)

    media_group_id = Column(Integer, default=None)
    media_file_id = Column(String, default=None)
    media_file_unique_id = Column(String, default=None)
    media_type = Column(String, default=None)

    hashtags = Column(String, default=None)  # hashtag entities as json string

    dates_from_hashtags = Column(Boolean, default=False)

    send_validity_notifications = Column(Boolean, default=True)
    validity_notification_chat_id = Column(Integer, default=None)
    validity_notification_message_id = Column(Integer, default=None)
    validity_notification_sent_on = Column(DateTime, default=None)
    validity_notification_message_json = Column(String, default=None)

    created_on = Column(DateTime, default=utilities.now)
    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)
    message_json = Column(String, default=None)

    deleted = Column(Boolean, default=False)  # != Event.canceled
    deleted_on = Column(DateTime, default=None)
    deletion_reason = Column(Integer, default=DeletionReason.OTHER)
    not_a_party = Column(Boolean, default=False)

    localata = Column(Boolean, default=False)

    chat: Chat = relationship("Chat")

    def __init__(self, chat_id: int, message_id: int):
        self.message_id = message_id
        self.chat_id = chat_id

    def updated(self):
        self.updated_on = utilities.now()

    def title_escaped(self):
        return f"{utilities.escape_html(self.event_title)}"

    def title_link_html(self):
        return self.message_link_html(self.event_title)

    def delete(self, reason: Optional[int] = None):
        self.deleted = True
        self.deleted_on = utilities.now()
        if reason:
            self.deletion_reason = reason

    def is_valid(self) -> bool:
        """an event is valid if it has a title and either:
        - has a start month/year
        - is marked as soon"""

        # we basically save any channel post that has a text/caption as an Event, so there might be non-valid Event
        valid = self.event_title and not self.not_a_party and ((self.start_month and self.start_year) or self.soon)  # and self.get_hashtags()
        return bool(valid)

    def is_valid_from_parsing(self):
        """returns true if the event is_valid() and its dates do not come from the month hashtag,
        but from parsing the text"""

        return self.is_valid() and not self.dates_from_hashtags

    def message_link(self):
        chat_id_link = str(self.chat_id).replace("-100", "")
        return f"https://t.me/c/{chat_id_link}/{self.message_id}"

    def message_link_html(self, text: str):
        """will html-escape the provided text"""

        message_link = self.message_link()
        return f"<a href=\"{message_link}\">{utilities.escape_html(text)}</a>"

    def discussion_group_message_link(self):
        chat_id_link = str(self.discussion_group_chat_id).replace("-100", "")
        return f"https://t.me/c/{chat_id_link}/{self.discussion_group_message_id}"

    def discussion_group_message_link_html(self, text: str):
        """will html-escape the provided text"""

        message_link = self.discussion_group_message_link()
        return f"<a href=\"{message_link}\">{utilities.escape_html(text)}</a>"

    def save_discussion_group_message(self, message: Message):
        self.discussion_group_chat_id = message.chat.id
        self.discussion_group_message_id = message.message_id
        self.discussion_group_received_on = message.date
        self.discussion_group_message_json = json.dumps(message.to_dict(), indent=2)

    def save_validity_notification_message(self, message: Message):
        self.validity_notification_chat_id = message.chat.id
        self.validity_notification_message_id = message.message_id
        self.validity_notification_sent_on = message.date
        self.validity_notification_message_json = json.dumps(message.to_dict(), indent=2)

    def icon(self):
        if not self.event_type:
            return Emoji.QUESTION
        if self.event_type == EventType.FREE:
            return Emoji.PIRATE
        if self.event_type == EventType.STREET_PARADE:
            return Emoji.TRUCK
        if self.event_type == EventType.LEGAL:
            return Emoji.TICKET
        if self.event_type == EventType.CS_OR_SQUAT:
            return Emoji.COMRADE
        if self.event_type == EventType.PRIVATE:
            return Emoji.HOUSE
        if self.event_type == EventType.OTHER:
            return Emoji.SPEAKER

    def start_date_as_str(self):
        start_date = None
        if self.start_month and self.start_year:
            start_day = f"{self.start_day:02}" if self.start_day else "??"
            start_date = f"{start_day}.{self.start_month:02}.{self.start_year}"

        return start_date

    def start_date_as_date(self, fill_missing_day: int = 0):
        if not self.start_month or not self.start_year:
            return
        if not self.start_day and not fill_missing_day:
            return

        start_day = self.start_day if self.start_day else fill_missing_day
        start_date = datetime.date(self.start_year, self.start_month, start_day)

        return start_date

    def end_date_as_date(self, fill_missing_day: int = 0):
        if not self.end_month or not self.end_year:
            return
        if not self.end_day and not fill_missing_day:
            return

        end_day = self.end_day if self.end_day else fill_missing_day
        end_date = datetime.date(self.end_year, self.end_month, end_day)

        return end_date

    def end_date_as_str(self):
        end_date = None
        if self.end_month and self.end_year:
            end_day = f"{self.end_day:02}" if self.end_day else "??"
            end_date = f"{end_day}.{self.end_month:02}.{self.end_year}"

        return end_date

    def dates_as_str(self):
        return self.start_date_as_str(), self.end_date_as_str()

    def dates_as_date(self, fill_missing_day: int = 0):
        return self.start_date_as_date(fill_missing_day), self.end_date_as_date(fill_missing_day)

    def single_day(self):
        """wether the event is a single-day event or not"""

        # avoid "int == None" comparision
        start_day = self.start_day or 0
        end_day = self.end_day or 0

        return start_day == end_day and self.start_month == self.end_month and self.start_year == self.end_year

    def populate_date_fields(self):
        """if we know the start and end dates, make sure the Date fields are set"""

        if self.start_year and self.start_month and self.start_day:
            self.start_date = self.start_date_as_date()
            self.start_week = self.start_date.isocalendar()[1]
        if self.end_year and self.end_month and self.end_day:
            self.end_date = self.end_date_as_date()

    def reset_date_fields(self):
        self.start_day = None
        self.start_month = None
        self.start_year = None
        self.start_date = None

        self.end_day = None
        self.end_month = None
        self.end_year = None
        self.end_date = None

    def pretty_date(self, week_number=False) -> str:
        if not self.start_month or not self.start_year:
            return "??.??.????"

        start_day = f"{self.start_day:02}" if self.start_day else "??"
        week_number = "" if not week_number or not self.start_week else f" (W{self.start_week})"

        if not self.single_day():
            end_day = f"{self.end_day:02}" if self.end_day else "??"
            if self.start_year != self.end_year:
                return f"{start_day}.{self.start_month:02}.{self.start_year}-{end_day}.{self.end_month:02}.{self.end_year}{week_number}"
            elif self.start_month != self.end_month:
                return f"{start_day}.{self.start_month:02}-{end_day}.{self.end_month:02}.{self.end_year}{week_number}"
            else:
                return f"{start_day}-{end_day}.{self.start_month:02}.{self.start_year}{week_number}"

        logger.info(f"{self.start_month}, {self.end_month}")

        return f"{start_day}.{self.start_month:02}.{self.start_year}{week_number}"

    def save_hashtags(self, hashtags_list: List):
        self.hashtags = json.dumps(hashtags_list, indent=2)

    def get_hashtags(self) -> List:
        if not self.hashtags:
            return []
        return json.loads(self.hashtags)

    def to_dict(self):
        return {field.name: getattr(self, field.name) for field in self.__table__.c}

    def __repr__(self):
        # logger.info(f"Event.__repr__")
        return f"Event(origin={self.chat_id}/{self.message_id}, title=\"{self.event_title}\", date={self.pretty_date()}, link={self.message_link()})"


class PartiesMessage(Base):
    __tablename__ = 'parties_messages'
    __allow_unmapped__ = True

    chat_id = Column(Integer, ForeignKey('chats.chat_id'), primary_key=True)
    message_id = Column(Integer, primary_key=True)
    events_type = Column(String, nullable=False)

    # info about the channel post that was forwarded to the discussion group
    discussion_group_chat_id = Column(Integer, default=None)
    discussion_group_message_id = Column(Integer, default=None)
    discussion_group_received_on = Column(DateTime, default=None)
    discussion_group_message_json = Column(String, default=None)
    discussion_group_message_deleted = Column(Boolean, default=False)  # deleted by the bot

    message_date = Column(DateTime, default=None)
    message_edit_date = Column(DateTime, default=None)

    force_sent = Column(Boolean, default=False)
    deleted = Column(Boolean, default=False)
    ignore = Column(Boolean, default=False)
    events_list = Column(String, default=json.dumps([]))

    created_on = Column(DateTime, default=utilities.now)
    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)
    message_json = Column(String, default=None)

    chat: Chat = relationship("Chat")

    def __init__(self, message: Message, events_type: str, events_list: Optional[List] = None, force_sent=False):
        self.message_id = message.message_id
        self.chat_id = message.chat.id
        self.message_date = message.date
        self.events_type = events_type
        self.force_sent = force_sent
        self.message_json = json.dumps(message.to_dict(), indent=2)
        if events_list:
            self.save_events(events_list)

    def save_edited_message(self, edited_message: Message):
        self.message_edit_date = edited_message.edit_date
        self.message_json = json.dumps(edited_message.to_dict(), indent=2)

    def save_discussion_group_message(self, message: Message):
        self.discussion_group_chat_id = message.chat.id
        self.discussion_group_message_id = message.message_id
        self.discussion_group_received_on = message.date
        self.discussion_group_message_json = json.dumps(message.to_dict(), indent=2)

    def message_link(self, text: str = ""):
        chat_id_link = str(self.chat_id).replace("-100", "")
        message_link = f"https://t.me/c/{chat_id_link}/{self.message_id}"
        if not text:
            return message_link
        return f"<a href=\"{message_link}\">{utilities.escape_html(text)}</a>"

    def save_events(self, events_list: List):
        self.events_list = json.dumps(events_list, indent=2)

    def compare_events(self, events_list: List, save=True):
        same_events = set(events_list) == set(self.events_list)
        if not same_events and save:
            self.save_events(events_list)

        return same_events

    def isoweek(self):
        return self.message_date.isocalendar()[1]


class ApplicationRequest(Base):
    __tablename__ = 'application_requests'
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True)
    user_id = mapped_column(Integer, ForeignKey('users.user_id'))
    ready = Column(Boolean, default=False)  # ready to be sent to staff
    status = Column(Boolean, default=None)
    reset = Column(Boolean, default=False)
    status_notes = Column(String, default=None)
    status_changed_on = Column(DateTime, default=None)
    # canceled = Column(Boolean, default=False)

    request_sent_message_message_id = Column(Integer, default=None)  # message_id of the message we sent to the user saying that their request has been sent to the staff
    accepted_message_message_id = Column(Integer, default=None)  # message notifying the user that they were accepted

    invite_link = Column(String, default=None)  # the invite link we sent to the user
    invite_link_can_be_revoked_after_join = Column(Boolean, default=False)  # wether it is safe to revoke the invite link after the user joined
    invite_link_revoked = Column(Boolean, default=False)  # wether 'invite_link' has been revoked or not

    other_members_text = Column(String, default=None)
    other_members_message_id = Column(Integer, default=None)
    other_members_received_on = Column(DateTime, default=None)

    social_text = Column(String, default=None)
    social_message_id = Column(Integer, default=None)
    social_received_on = Column(DateTime, default=None)

    log_message_chat_id = mapped_column(Integer, ForeignKey('chats.chat_id'), default=None)
    log_message_message_id = Column(Integer, default=None)
    log_message_text_html = Column(String, default=None)
    log_message_posted_on = Column(DateTime, default=None)
    log_message_json = Column(String, default=None)

    staff_message_chat_id = mapped_column(Integer, ForeignKey('chats.chat_id'), default=None)
    staff_message_message_id = Column(Integer, default=None)
    staff_message_text_html = Column(String, default=None)
    staff_message_posted_on = Column(DateTime, default=None)
    staff_message_json = Column(String, default=None)

    handled_by_user_id = mapped_column(Integer, ForeignKey('users.user_id'), default=None)  # admin that changed the status

    created_on = Column(DateTime, default=utilities.now)
    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)

    user: User = relationship("User", foreign_keys=user_id)
    handled_by: User = relationship("User", foreign_keys=handled_by_user_id)
    log_message_chat: Chat = relationship("Chat", foreign_keys=log_message_chat_id)
    staff_message_chat: Chat = relationship("Chat", foreign_keys=staff_message_chat_id)
    description_messages: List[Mapped['DescriptionMessage']] = relationship("DescriptionMessage", back_populates="application_request")

    def __init__(self, user_id: int):
        self.user_id = user_id

    def is_pending(self):
        return self.status is None

    def rejected(self):
        return self.status is False

    def accepted(self):
        return self.status is True

    def status_pretty(self):
        if self.status is None:
            return "pending"
        elif self.status is True:
            return "accepted"
        else:
            return "rejected"

    def media_messages_count(self):
        return len([m for m in self.description_messages if m.can_be_grouped()])

    def total_text_length(self):
        total_length = 0
        for message in self.description_messages:
            if message.text_html:
                total_length += len(message.text_html)

        return total_length

    def save_other_members(self, message: Message):
        self.other_members_text = message.text_html
        self.other_members_message_id = message.message_id
        self.other_members_received_on = utilities.now()

    def save_social(self, message: Message):
        self.social_text = message.text_html or message.caption_html
        self.social_message_id = message.message_id
        self.social_received_on = utilities.now()

    def set_log_message(self, message: Message):
        self.log_message_chat_id = message.chat.id
        self.log_message_message_id = message.message_id
        self.log_message_text_html = message.text_html
        self.log_message_posted_on = utilities.now()
        if config.settings.db_save_json:
            self.log_message_json = json.dumps(message.to_dict(), indent=2)

    def set_staff_message(self, message: Message):
        self.staff_message_chat_id = message.chat.id
        self.staff_message_message_id = message.message_id
        self.staff_message_text_html = message.text_html
        self.staff_message_posted_on = utilities.now()
        if config.settings.db_save_json:
            self.staff_message_json = json.dumps(message.to_dict(), indent=2)

    def update_staff_chat_message(self, message: Message):
        self.staff_message_text_html = message.text_html
        if config.settings.db_save_json:
            self.staff_message_json = json.dumps(message.to_dict(), indent=2)

    def update_log_chat_message(self, message: Message):
        self.log_message_text_html = message.text_html
        if config.settings.db_save_json:
            self.log_message_json = json.dumps(message.to_dict(), indent=2)

    def log_message_link(self):
        chat_id = str(self.log_message_chat_id).replace("-100", "")
        return f"https://t.me/c/{chat_id}/{self.log_message_message_id}"

    def staff_message_link(self, text: Optional[str] = None):
        chat_id = str(self.staff_message_chat_id).replace("-100", "")
        link = f"https://t.me/c/{chat_id}/{self.staff_message_message_id}"
        if not text:
            return link

        return f"<a href\"{link}\">{utilities.escape(text)}</a>"

    def accept(self, by_user_id: int, notes: Optional[str] = None):
        self.status = True
        self.handled_by_user_id = by_user_id
        self.status_changed_on = utilities.now()
        self.status_notes = notes

    def reject(self, by_user_id: int, notes: Optional[str] = None):
        self.status = False
        self.handled_by_user_id = by_user_id
        self.status_changed_on = utilities.now()
        self.status_notes = notes

    def set_invite_link(self, invite_link: str, can_be_revoked: bool):
        self.invite_link = invite_link
        self.invite_link_can_be_revoked_after_join = can_be_revoked

    def sent_to_staff(self):
        return bool(self.staff_message_message_id)


class DescriptionMessageType:
    OTHER_MEMBERS = "other_members"
    SOCIAL = "social"
    # types of description message
    TEXT = "text"
    VOICE = "voice"
    PHOTO = "photo"
    VIDEO = "video"
    VIDEO_MESSAGE = "video_message"


class DescriptionMessage(Base):
    __tablename__ = 'description_messages'
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True)
    application_request_id = mapped_column(Integer, ForeignKey('application_requests.id'))
    user_id = mapped_column(Integer, ForeignKey('users.user_id'))
    message_id = Column(Integer, nullable=False)
    reply_to_message_id = Column(Integer, default=None)

    # right now, OTHER_MEMBERS and SOCIAL are actually saved in ApplicationRequest
    type = Column(String, nullable=False)

    datetime = Column(DateTime, default=None)
    edited_on = Column(DateTime, default=None)

    text = Column(String, default=None)
    text_html = Column(String, default=None)
    caption = Column(String, default=None)
    caption_html = Column(String, default=None)
    media_type = Column(String, default=None)
    media_file_id = Column(String, default=None)
    media_unique_id = Column(String, default=None)
    media_group_id = Column(String, default=None)

    message_json = Column(String, default=None)

    log_message_chat_id = mapped_column(Integer, ForeignKey('chats.chat_id'), default=None)
    log_message_message_id = Column(Integer, default=None)
    log_message_json = Column(String, default=None)

    # relationships
    application_request: ApplicationRequest = relationship("ApplicationRequest", back_populates="description_messages")
    user: User = relationship("User")

    def __init__(self, application_request_id: int, message: Message, message_type: Optional[str] = None):
        self.application_request_id = application_request_id
        self.user_id = message.from_user.id
        self.message_id = message.message_id

        self.text = message.text
        self.text_html: str = message.text_html
        self.caption = message.caption
        self.caption_html: str = message.caption_html
        self.media_group_id = message.media_group_id
        self.datetime = message.date

        if message.reply_to_message:
            self.reply_to_message_id = message.reply_to_message.message_id

        if message_type:
            # "social" or "other_members"
            self.type = message_type
        else:
            if message.text:
                self.type = DescriptionMessageType.TEXT
            else:
                if message.photo:
                    self.type = DescriptionMessageType.PHOTO
                    self.media_file_id = message.photo[-1].file_id
                    self.media_unique_id = message.photo[-1].file_unique_id
                elif message.video:
                    self.type = DescriptionMessageType.VIDEO
                    self.media_file_id = message.video.file_id
                    self.media_unique_id = message.video.file_unique_id
                elif message.voice:
                    self.type = DescriptionMessageType.VOICE
                    self.media_file_id = message.voice.file_id
                    self.media_unique_id = message.voice.file_unique_id
                elif message.video_note:
                    self.type = DescriptionMessageType.VIDEO_MESSAGE
                    self.media_file_id = message.video_note.file_id
                    self.media_unique_id = message.video_note.file_unique_id

        if config.settings.db_save_json:
            self.message_json = json.dumps(message.to_dict(), indent=2)

    def is_other_members_message(self):
        return self.type == DescriptionMessageType.OTHER_MEMBERS

    def is_social_message(self):
        return self.type == DescriptionMessageType.SOCIAL

    def is_description_message(self):
        return self.type in (
            DescriptionMessageType.TEXT,
            DescriptionMessageType.PHOTO,
            DescriptionMessageType.VOICE,
            DescriptionMessageType.VIDEO,
            DescriptionMessageType.VIDEO_MESSAGE,
        )

    def can_be_grouped(self):
        return self.type in (DescriptionMessageType.PHOTO, DescriptionMessageType.VIDEO)

    def get_input_media(self):
        if self.type == DescriptionMessageType.PHOTO:
            return InputMediaPhoto(self.media_file_id, caption=self.caption_html)
        elif self.type == DescriptionMessageType.VIDEO:
            return InputMediaVideo(self.media_file_id, caption=self.caption_html)

    def set_log_message(self, message: Message):
        self.log_message_chat_id = message.chat.id
        self.log_message_message_id = message.message_id
        self.log_message_json = json.dumps(message.to_dict(), indent=2)

    def log_message_link(self):
        chat_id = str(self.log_message_chat_id).replace("-100", "")
        return f"https://t.me/c/{chat_id}/{self.log_message_message_id}"


class HashingVersion:
    CURRENT = 1


class StaffChatMessage(Base):
    __tablename__ = 'staff_chat_messages'
    __allow_unmapped__ = True

    chat_id = Column(Integer, ForeignKey('chats.chat_id'), primary_key=True)
    message_id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey('users.user_id'), default=None, nullable=True)
    is_topic_message = Column(Boolean, default=False)
    message_thread_id = Column(Integer, default=None)
    message_date = Column(DateTime, default=None)
    message_edit_date = Column(DateTime, default=None)
    deleted = Column(Boolean, default=False)

    text_hash = Column(String, default=None)
    text_hashing_version = Column(Integer, default=None)

    media_file_id = Column(String, default=None)
    media_file_unique_id = Column(String, default=None)
    media_group_id = Column(Integer, default=None)
    media_type = Column(String, default=None)

    message_json = Column(String, default=None)
    created_on = Column(DateTime, default=utilities.now)
    updated_on = Column(DateTime, default=utilities.now, onupdate=utilities.now)

    chat: Chat = relationship("Chat")

    Index('index_text_hash', text_hash)
    Index('index_media_file_unique_id', media_file_unique_id)

    def __init__(self, message: Message):
        self.update_message_metadata(message)

    def update_message_metadata(self, message: Message):
        self.chat_id = message.chat.id
        self.message_id = message.message_id

        self.message_thread_id = message.message_thread_id
        self.is_topic_message = message.is_topic_message
        self.message_date = message.date
        self.message_edit_date = message.edit_date
        if config.settings.db_save_json:
            self.message_json = json.dumps(message.to_dict(), indent=2)

        text = message.text or message.caption
        if text:
            self.text_hash = utilities.generate_text_hash(text)
            self.text_hashing_version = HashingVersion.CURRENT

        if utilities.contains_media_with_file_id(message):
            media_file_id, media_file_unique_id, media_group_id = utilities.get_media_ids(message)
            self.media_file_id = media_file_id
            self.media_file_unique_id = media_file_unique_id
            self.media_group_id = media_group_id
            self.media_type = utilities.detect_media_type(message, raise_on_unknown_type=False)

    def message_link(self):
        chat_id = str(self.chat_id).replace("-100", "")
        base_link = f"https://t.me/c/{chat_id}/{self.message_id}"

        if self.is_topic_message and self.message_thread_id:
            base_link = f"{base_link}?thread={self.message_thread_id}"

        return base_link

    def message_link_html(self, text: str):
        """will html-escape the provided text"""

        message_link = self.message_link()
        return f"<a href=\"{message_link}\">{utilities.escape_html(text)}</a>"


class Destination:
    EVENTS_CHAT_DEEPLINK = "events-chat-deeplink"
    USERS_CHAT_DEEPLINK = "users-chat-deeplink"


class InviteLink(Base):
    __tablename__ = 'invite_links'
    __allow_unmapped__ = True

    link_id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey('chats.chat_id'))

    destination = Column(String, default=None)
    created_on = Column(DateTime, default=None)

    used_by_user_id = Column(Integer, ForeignKey('users.user_id'), default=None, nullable=True)
    used_on = Column(DateTime, default=None)

    # info about who we generated the invite link for
    sent_to_user_user_id = Column(Integer, ForeignKey('users.user_id'), default=None, nullable=True)
    sent_to_user_message_id = Column(Integer, default=None)
    sent_to_user_message_ids_to_delete = Column(String, default=None)  # json, messages we might want to delete once the link is used
    sent_to_user_via_reply_markup = Column(Boolean, default=False)
    sent_to_user_link_removed = Column(Boolean, default=False)  # wether we removed if from the message
    sent_to_user_on = Column(DateTime, default=None)

    # from https://core.telegram.org/bots/api#chatinvitelink
    invite_link = Column(String, default=None)
    creator_user_id = Column(Integer, ForeignKey('users.user_id'), default=None, nullable=True)
    creates_join_request = Column(Boolean, default=False)
    is_primary = Column(Boolean, default=False)
    is_revoked = Column(Boolean, default=False)
    name = Column(String, default=None)
    expire_date = Column(DateTime, default=None)
    member_limit = Column(Integer, default=None)
    pending_join_request_count = Column(Integer, default=None)

    # other
    can_be_revoked = Column(Boolean, default=True)
    revoked_on = Column(DateTime, default=None)

    chat: Chat = relationship("Chat")

    def __init__(
            self,
            chat_id: int,
            destination: Optional[str] = None,
            invite_link: Optional[str] = None,
            creator_user_id: Optional[int] = None,
            creates_join_request: bool = False,
            is_primary: bool = False,
            is_revoked: bool = False,
            name: Optional[str] = None,
            expire_date: Optional[datetime.datetime] = None,
            member_limit: Optional[int] = None,
            pending_join_request_count: Optional[int] = None
    ):
        self.chat_id = chat_id
        self.destination = destination
        self.invite_link = invite_link
        self.creator_user_id = creator_user_id
        self.creates_join_request = creates_join_request
        self.is_primary = is_primary
        self.is_revoked = is_revoked
        self.name = name
        self.expire_date = expire_date
        self.member_limit = member_limit
        self.pending_join_request_count = pending_join_request_count
        self.created_on = utilities.now()
        # print(self.created_on.tzinfo)

    @classmethod
    def from_chat_invite_link(cls, chat_id: int, chat_invite_link: ChatInviteLink, destination: Optional[str] = None):
        return cls(
            chat_id=chat_id,
            destination=destination,
            invite_link=chat_invite_link.invite_link,
            creator_user_id=chat_invite_link.creator.id,
            creates_join_request=chat_invite_link.creates_join_request,
            is_primary=chat_invite_link.is_primary,
            is_revoked=chat_invite_link.is_revoked,
            name=chat_invite_link.name,
            expire_date=chat_invite_link.expire_date,
            member_limit=chat_invite_link.member_limit,
            pending_join_request_count=chat_invite_link.pending_join_request_count
        )

    def save_sent_to_user_message_data(self, message: Message, message_ids_to_delete: Optional[Iterable] = None, via_reply_markup: bool = False):
        self.sent_to_user_user_id = message.chat.id
        self.sent_to_user_message_id = message.message_id
        if message_ids_to_delete:
            self.save_message_ids_to_delete(message_ids_to_delete)
        self.sent_to_user_via_reply_markup = via_reply_markup
        self.sent_to_user_on = message.date

    def revoked(self, revoked_on: Optional[datetime.datetime] = None):
        self.is_revoked = True
        self.revoked_on = revoked_on or utilities.now()

    def used_by(self, user: Union[int, TelegramUser], used_on: Optional[datetime.datetime] = None):
        if isinstance(user, int):
            self.used_by_user_id = user
        else:
            self.used_by_user_id = user.id

        self.used_on = used_on or utilities.now()

    def save_message_ids_to_delete(self, message_ids_to_delete: Iterable):
        self.sent_to_user_message_ids_to_delete = json.dumps(message_ids_to_delete, indent=2)

    def extend_message_ids_to_delete(self, new_message_ids: Iterable):
        existing_message_ids = self.get_message_ids_to_delete()
        existing_message_ids.extend(new_message_ids)
        self.save_message_ids_to_delete(existing_message_ids)

    def get_message_ids_to_delete(self):
        if not self.sent_to_user_message_ids_to_delete:
            return []

        return json.loads(self.sent_to_user_message_ids_to_delete)
