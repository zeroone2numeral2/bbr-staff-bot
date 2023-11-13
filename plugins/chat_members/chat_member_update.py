import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update, ChatMemberUpdated, Bot, Chat as TelegramChat
from telegram.error import TelegramError, BadRequest
from telegram.ext import ChatMemberHandler, CallbackContext

from constants import Group
from database.models import User, Chat, ChatMember as DbChatMember, Destination
from database.queries import users, chats, invite_links
from emojis import Emoji
from plugins.chat_members.common import (
    save_or_update_users_from_chat_member_update,
    save_chat_member
)
import decorators
import utilities

logger = logging.getLogger(__name__)


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


async def revoke_invite_link_safe(bot: Bot, chat_id: int, invite_link: str) -> bool:
    logger.info(f"revoking invite link {invite_link}...")
    try:
        await bot.revoke_chat_invite_link(chat_id, invite_link)
        return True
    except (BadRequest, TelegramError) as e:
        logger.error(f"error while revoking invite link: {e}")
        return False


async def handle_events_chat_join_via_bot_link(session: Session, bot: Bot, chat_member_updated: ChatMemberUpdated):
    invite_link = invite_links.get_invite_link(session, chat_member_updated.invite_link.invite_link)
    if not invite_link:
        logger.info(f"couldn't find {chat_member_updated.invite_link.invite_link} in the database")
        return

    invite_link.used_by(chat_member_updated.new_chat_member.user, used_on=chat_member_updated.date)

    if invite_link.destination == Destination.EVENTS_CHAT_DEEPLINK:
        # do not revoke for other destinations
        logger.info(f"link destination is {invite_link.destination}")
        success = await revoke_invite_link_safe(bot, invite_link.chat_id, invite_link.invite_link)
        if success:
            invite_link.revoked()

        message_ids_to_delete = invite_link.get_message_ids_to_delete()
        if message_ids_to_delete:
            logger.info("deleting messages...")
            for message_id in message_ids_to_delete:
                success = await utilities.delete_messages_by_id_safe(bot, invite_link.sent_to_user_user_id, message_id)
                if success and message_id == invite_link.sent_to_user_message_id:
                    # mark the invite link as removed from the user's chat if deleting the message with the link was successful
                    logger.info("saving invite link removal from the user's chat...")
                    invite_link.sent_to_user_link_removed = True


async def handle_users_chat_join(session: Session, chat: Chat, bot: Bot, chat_member_updated: ChatMemberUpdated):
    user: User = users.get_safe(session, chat_member_updated.new_chat_member.user)
    if not user.last_request_id or user.last_request.is_pending() or user.last_request.status is False:
        # user joined the chat without going through the approval process, or their request was rejected

        if not chat_member_updated.invite_link:
            logger.info("user was added by an admin and didn't join by invite link")
            # do not log manual additions
            return

        logger.debug("no last request to check or last request is pending: we log the join")
        log_chat = chats.get_chat(session, Chat.is_log_chat)

        user_mention = user.mention()

        if chat_member_updated.invite_link.is_primary:
            invite_link_name = "link d'invito primario"
        elif chat_member_updated.invite_link.name:
            invite_link_name = f"\"{utilities.escape_html(chat_member_updated.invite_link.name)}\""
        else:
            invite_link_name = "senza nome"

        invite_link_id = utilities.extract_invite_link_id(chat_member_updated.invite_link.invite_link)
        created_by = chat_member_updated.invite_link.creator
        admin_mention = created_by.mention_html(utilities.escape_html(created_by.full_name))
        text = f"{Emoji.LINK} <b>#JOIN_SENZA_RICHIESTA</b> di {user_mention} • #id{user.user_id}\n\n" \
               f"link: #link{invite_link_id} ({invite_link_name})\n" \
               f"generato da: {admin_mention} • #admin{created_by.id}"

        await bot.send_message(log_chat.chat_id, text)
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
        success = await revoke_invite_link_safe(bot, chat.chat_id, user.last_request.invite_link)
        user.last_request.invite_link_revoked = success


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_chat_member_update(update: Update, context: CallbackContext, session: Session, chat: Optional[Chat] = None):
    logger.info(f"chat member update {utilities.log(update)}")

    if not chat.is_special_chat() and not chat.save_chat_members:
        logger.info(f"chat is not a special chat and save_chat_members is false: ignoring update")
        return

    logger.info("saving or updating User objects...")
    save_or_update_users_from_chat_member_update(session, update, commit=True)
    if update.effective_chat.type in (TelegramChat.CHANNEL, TelegramChat.SUPERGROUP):
        logger.info("saving or updating Chat object...")
        save_or_update_chat_from_chat_member_update(session, update, commit=True)

    logger.info("saving new chat_member object...")
    db_member_record: DbChatMember = save_chat_member(session, update)

    if db_member_record.is_member():
        # mark the user as "has_been_member" even if it isn't the users chat
        db_member_record.has_been_member = True

    if utilities.is_left_update(update.chat_member):
        # do nothing for now, delete history maybe?
        logger.info("user was member and left the chat")
        return

    if utilities.is_join_update(update.chat_member) and chat.is_users_chat:
        logger.info("user joined the users chat")
        await handle_users_chat_join(session, chat, context.bot, update.chat_member)

    if utilities.is_join_update(update.chat_member) and chat.is_events_chat:
        if update.chat_member.invite_link and update.chat_member.invite_link.creator.id == context.bot.id:
            logger.info("user joined events chat with a link created by the bot")
            await handle_events_chat_join_via_bot_link(session, context.bot, update.chat_member)


HANDLERS = (
    (ChatMemberHandler(on_chat_member_update, ChatMemberHandler.CHAT_MEMBER), Group.NORMAL),
)
