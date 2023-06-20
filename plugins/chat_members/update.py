import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update, ChatMemberUpdated, Bot
from telegram import ChatMember, ChatMemberMember, ChatMemberRestricted, ChatMemberLeft, ChatMemberBanned, ChatMemberAdministrator
from telegram.error import TelegramError, BadRequest
from telegram.ext import ChatMemberHandler, CallbackContext

from constants import Group
from database.models import User, Chat, ChatMember as DbChatMember
from database.queries import users, chats
import decorators
import utilities

logger = logging.getLogger(__name__)


def save_or_update_users_from_chat_member_update(session: Session, update: Update, commit=False) -> List[User]:
    users_to_save = []
    if update.chat_member:
        users_to_save = [update.chat_member.from_user, update.chat_member.new_chat_member.user]
    elif update.my_chat_member:
        users_to_save = [update.my_chat_member.from_user]

    user_records = []
    for telegram_user in users_to_save:
        user = users.get_or_create(session, telegram_user.id, create_if_missing=False)
        if not user:
            user = User(telegram_user)
            session.add(user)
        else:
            user.update_metadata(telegram_user)
        user_records.append(user)

    if commit:
        session.commit()

    return user_records


def save_or_update_chat_from_chat_member_update(session: Session, update: Update, commit=False) -> List[Chat]:
    if update.effective_chat.id > 0:
        raise ValueError("couldn't save chat_id > 0")

    chat = chats.get_or_create(session, update.effective_chat.id, create_if_missing=False)
    if not chat:
        chat = Chat(update.effective_chat)
        session.add(chat)
    else:
        chat.update_metadata(update.effective_chat)

    if commit:
        session.commit()

    return [chat]


def save_chat_member(session: Session, update: Update, commit=False) -> DbChatMember:
    if update.chat_member:
        logger.debug(f"saving ChatMember, new user status: <{update.chat_member.new_chat_member.status}>")
        # from pprint import pprint
        # pprint(update.chat_member.to_dict())
        chat_member_to_save = update.chat_member.new_chat_member
    elif update.my_chat_member:
        logger.debug(f"saving MyChatMember, new bot status: <{update.my_chat_member.new_chat_member.status}>")
        # from pprint import pprint
        # pprint(update.my_chat_member.to_dict())
        chat_member_to_save = update.my_chat_member.new_chat_member
    else:
        raise ValueError("couldn't find ChatMember to save")

    chat_member_record = DbChatMember.from_chat_member(update.effective_chat.id, chat_member_to_save)
    session.merge(chat_member_record)

    if commit:
        session.commit()

    return chat_member_record


async def handle_new_member(session: Session, chat: Chat, bot: Bot, chat_member_updated: ChatMemberUpdated):
    logger.info("user joined users chat")
    user: User = users.get_safe(session, chat_member_updated.new_chat_member.user)
    if not user.last_request_id:
        logger.debug("no last request to check")
        return

    if user.last_request.accepted_message_message_id:
        # always remove the inline keyboard
        logger.debug(f"removing keyboard from message_id {user.last_request.accepted_message_message_id}")
        try:
            await bot.edit_message_reply_markup(
                user.user_id,
                user.last_request.accepted_message_message_id,
                reply_markup=None
            )
        except (TelegramError, BadRequest) as e:
            logger.error(f"error while removing reply makrup: {e}")

    if user.last_request.invite_link_can_be_revoked_after_join and not user.last_request.invite_link_revoked:
        logger.info(f"revoking invite link {user.last_request.invite_link}...")
        try:
            await bot.revoke_chat_invite_link(chat.chat_id, user.last_request.invite_link)
            user.last_request.invite_link_revoked = True
        except (BadRequest, TelegramError) as e:
            logger.error(f"error while revoking invite link: {e}")


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_chat_member_update(update: Update, context: CallbackContext, session: Session, chat: Optional[Chat] = None):
    logger.info(f"chat member update {utilities.log(update)}")

    logger.info("saving or updating User objects...")
    save_or_update_users_from_chat_member_update(session, update, commit=True)
    if update.effective_chat.id < 0:
        logger.info("saving or updating Chat object...")
        save_or_update_chat_from_chat_member_update(session, update, commit=True)

    logger.info("saving new chat_member object...")
    chat_member_record: DbChatMember = save_chat_member(session, update)

    if not utilities.is_join_update(update.chat_member):
        return

    # mark the user as "has_been_member" even if it isn't the users chat
    chat_member_record.has_been_member = True

    if not chat.is_users_chat:
        return

    await handle_new_member(session, chat, context.bot, update.chat_member)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_my_chat_member_update(update: Update, _, session: Session, chat: Optional[Chat] = None):
    logger.info(f"my chat member update {utilities.log(update)}")

    logger.info("saving or updating User objects...")
    user_records = save_or_update_users_from_chat_member_update(session, update, commit=True)

    if update.effective_chat.id > 0:
        user = user_records[0]  # only one will be returned
        new_status = update.my_chat_member.new_chat_member.status
        logger.info(f"MyChatMember update from private chat, new status: {new_status}")
        if new_status == ChatMember.BANNED:
            user.set_stopped()
        elif new_status == ChatMember.MEMBER:
            user.set_restarted()
        else:
            logger.warning(f"unhandled new status from MyChatMember update: {new_status}")
    else:
        logger.info(f"MyChatMember update in a group chat, new status: {update.my_chat_member.new_chat_member.status}")
        if isinstance(update.my_chat_member.new_chat_member, ChatMemberAdministrator):
            chat.set_as_administrator(
                can_delete_messages=update.my_chat_member.new_chat_member.can_delete_messages,
                can_invite_users=update.my_chat_member.new_chat_member.can_invite_users
            )
        elif isinstance(update.my_chat_member.new_chat_member, (ChatMemberMember, ChatMemberRestricted)):
            chat.unset_as_administrator()
        elif isinstance(update.my_chat_member.new_chat_member, (ChatMemberLeft, ChatMemberBanned)):
            chat.set_left()

        logger.info("saving new chat_member object...")
        save_chat_member(session, update)


HANDLERS = (
    (ChatMemberHandler(on_chat_member_update, ChatMemberHandler.CHAT_MEMBER), Group.NORMAL),
    (ChatMemberHandler(on_my_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER), Group.NORMAL),
)
