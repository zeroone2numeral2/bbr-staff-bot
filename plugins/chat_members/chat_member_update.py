import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update, ChatMemberUpdated, Bot, Chat as TelegramChat
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest
from telegram.ext import ChatMemberHandler, CallbackContext

import decorators
import utilities
from constants import Group
from database.models import User, Chat, ChatMember as DbChatMember, Destination
from database.queries import users, chats, invite_links
from emojis import Emoji
from plugins.chat_members.common import (
    save_or_update_users_from_chat_member_update,
    save_chat_member
)

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

    if invite_link.destination in (Destination.EVENTS_CHAT_DEEPLINK, Destination.USERS_CHAT_DEEPLINK):
        # do not revoke for other destinations
        logger.info(f"link destination is {invite_link.destination}")
        success = await revoke_invite_link_safe(bot, invite_link.chat_id, invite_link.invite_link)
        if success:
            invite_link.revoked()

        message_ids_to_delete = invite_link.get_message_ids_to_delete()
        if message_ids_to_delete:
            logger.info(f"deleting {len(message_ids_to_delete)} messages...")
            for message_id in message_ids_to_delete:
                success = await utilities.delete_messages_by_id_safe(bot, invite_link.sent_to_user_user_id, message_id)
                if success and message_id == invite_link.sent_to_user_message_id:
                    # mark the invite link as removed from the user's chat if deleting the message with the link was successful
                    logger.info("saving invite link removal from the user's chat...")
                    invite_link.sent_to_user_link_removed = True


async def remove_nojoin_hashtag(user: User, bot: Bot):
    logger.info(f"removing #nojoin hashtag from log message...")
    log_message_no_hashtag = user.last_request.log_message_text_html.replace(" • #nojoin", "")
    edited_log_message = await utilities.edit_text_by_ids_safe(
        bot=bot,
        chat_id=user.last_request.log_message_chat_id,
        message_id=user.last_request.log_message_message_id,
        text=f"{log_message_no_hashtag}"
    )
    if edited_log_message:
        user.last_request.update_log_chat_message(edited_log_message)


async def check_suspicious_join(session: Session, user: User, chat: Chat, bot: Bot, chat_member_updated: ChatMemberUpdated):
    user: User = users.get_safe(session, chat_member_updated.new_chat_member.user)
    added_by_admin = not chat_member_updated.invite_link and not chat_member_updated.via_chat_folder_invite_link
    if added_by_admin:
        logger.info("user was added by an admin (didn't join by invite link/folder link)")

    if not added_by_admin and (not user.last_request_id or user.last_request.is_pending() or user.last_request.rejected()):
        # user joined the chat without going through the approval process, or their request was rejected: log to channel
        # note about joins via folder link: when a user joins via a folder link, they actually
        # joined through the primary invite link of the admin that generated that folder invite link

        logger.debug("no last request to check or last request is pending/rejected: we log the join")
        log_chat = chats.get_chat(session, Chat.is_log_chat)

        user_mention = user.mention()

        if chat_member_updated.invite_link.is_primary:
            invite_link_name = "link d'invito primario"
        elif chat_member_updated.invite_link.name:
            invite_link_name = f"\"{utilities.escape_html(chat_member_updated.invite_link.name)}\""
        else:
            invite_link_name = "link senza nome"

        invite_link_id = utilities.extract_invite_link_id(chat_member_updated.invite_link.invite_link)
        created_by = chat_member_updated.invite_link.creator
        admin_mention = created_by.mention_html(utilities.escape_html(created_by.full_name))
        text = f"{Emoji.LINK} <b>#JOIN_SENZA_RICHIESTA</b> di {user_mention} • #id{user.user_id}\n\n" \
               f"link: #link{invite_link_id} ({invite_link_name})\n" \
               f"generato da: {admin_mention} • #admin{created_by.id}"

        if chat_member_updated.via_chat_folder_invite_link:
            text += (f"\n\n{Emoji.FOLDER} per unirsi, l'utente ha utilizzato il link generato da {admin_mention} per "
                     f"aggiungere la cartella del network")

        await bot.send_message(log_chat.chat_id, text)
        return


async def remove_and_revoke_invite_link(user: User, chat: Chat, bot: Bot):
    if user.last_request_id:
        # when a new member joins the users chat, always try to remove the last link we sent them
        if user.last_request.accepted_message_message_id:
            # always remove the inline keyboard
            logger.debug(f"removing keyboard from message_id {user.last_request.accepted_message_message_id}")
            await utilities.remove_reply_markup_safe(
                bot,
                user.user_id,
                user.last_request.accepted_message_message_id,
                raise_if_exception_is_not_message_not_modified=False  # do not raise an exception
            )

        if user.last_request.invite_link_can_be_revoked_after_join and not user.last_request.invite_link_revoked:
            # if the user was sent the folder link instead of a joinchat link, invite_link_can_be_revoked_after_join will be False
            success = await revoke_invite_link_safe(bot, chat.chat_id, user.last_request.invite_link)
            user.last_request.invite_link_revoked = success

        # we have to remove the #nojoin hashtag
        await remove_nojoin_hashtag(user, bot)


async def log_join_or_leave(user_left_or_kicked: bool, session: Session, bot: Bot, chat_member_updated: ChatMemberUpdated):
    user_joined = not user_left_or_kicked

    modlog_chat = chats.get_chat(session, Chat.is_modlog_chat)
    if not modlog_chat:
        logger.warning(f"no modlog chat set: we won't log join/leave")
        return

    chat = chat_member_updated.chat
    new_user = chat_member_updated.new_chat_member.user
    from_user = chat_member_updated.from_user

    event_type = "USCITA_UTENTE" if user_left_or_kicked else "INGRESO_UTENTE"
    event_emoji = Emoji.MOON if user_left_or_kicked else Emoji.SUN
    admin_action_type = "rimosso" if user_left_or_kicked else "aggiunto"

    chat_string = f"{Emoji.UFO} <b>#chat{str(chat.id).replace('-100', '')}</b> • {utilities.escape(chat.title)}"
    user_string = f"{Emoji.ALIEN} <b>#id{new_user.id}/b> • {utilities.mention_escaped(new_user)}"
    if new_user.username:
        user_string += f" • @{new_user.username}"

    text = f"{event_emoji} <b>#{event_type}</b>\n\n{chat_string}\n{user_string}"

    if from_user.id != new_user.id:
        # if different, the user was added/removed by an admin
        text += f"\n<b>{admin_action_type} da:</b> {utilities.mention_escaped(from_user)} • #admin{from_user.id}"
        text += f" (#modaction)"  # we can use this hashtag to search for actions that were taken by admins

    if chat_member_updated.invite_link:
        invite_link = chat_member_updated.invite_link
        if invite_link.is_primary:
            invite_link_name = "link d'invito primario"
        elif invite_link.name:
            invite_link_name = f"\"{utilities.escape_html(chat_member_updated.invite_link.name)}\""
        else:
            invite_link_name = "link senza nome"

        invite_link_id = utilities.extract_invite_link_id(invite_link.invite_link)
        created_by = invite_link.creator
        admin_mention = created_by.mention_html(utilities.escape_html(created_by.full_name))
        text += f"\n\n{Emoji.LINK} <b>link:</b> #link{invite_link_id} ({invite_link_name}) <b>generato da</b> {admin_mention} • #admin{created_by.id}"

        if chat_member_updated.via_chat_folder_invite_link:
            text += (f"\n{Emoji.FOLDER} per unirsi, l'utente ha utilizzato il link generato da {admin_mention} per "
                     f"aggiungere la cartella del network")

    if hasattr(chat_member_updated, "via_join_request") and chat_member_updated.via_join_request:
        # true if the user joined the chat after sending a direct join request without using an
        # invite link and being approved by an administrator. so when true, invite_link is probably not set
        text += f"\n{Emoji.DOOR} l'utente ha inviato una richiesta di unirsi senza utilizzare un link d'invito"

    await bot.send_message(modlog_chat.chat_id, text, parse_mode=ParseMode.HTML)


@decorators.catch_exception(silent=True)
@decorators.pass_session(pass_chat=True)
async def on_chat_member_update(update: Update, context: CallbackContext, session: Session, chat: Optional[Chat] = None):
    logger.info(f"chat member update {utilities.log(update)}")

    if chat.is_network_chat() or chat.save_chat_members:
        # update User, Chat and ChatMember only if it's a network chat, or we manually set to save ChatMembers

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

    user: User = users.get_safe(session, update.chat_member.new_chat_member.user)

    if not chat.is_network_chat():
        logger.info(f"chat is not a network chat: exiting")
        return

    if utilities.is_left_update(update.chat_member):
        # do nothing for now, delete history maybe?
        logger.info("user was member and left the chat")
        await log_join_or_leave(True, session, context.bot, update.chat_member)
        return

    if utilities.is_kicked_update(update.chat_member):
        logger.info("user was member and was kicked (not in the ban list)")
        await log_join_or_leave(True, session, context.bot, update.chat_member)
        return

    if utilities.is_banned_update(update.chat_member):
        logger.info("user was member and was banned")
        await log_join_or_leave(True, session, context.bot, update.chat_member)
        return

    if utilities.is_join_update(update.chat_member):
        logger.info("user joined a network chat")
        try:
            await log_join_or_leave(False, session, context.bot, update.chat_member)
        except Exception as e:
            logger.error(f"error while logging join: {e}", exc_info=True)

        await check_suspicious_join(session, user, chat, context.bot, update.chat_member)

        if chat.is_users_chat:
            logger.info("user joined the users chat: trying to remove and revoke invite link")
            await remove_and_revoke_invite_link(user, chat, context.bot)

        # this will check in the new InviteLink table and do what needs to be done with the invite link
        if update.chat_member.invite_link and update.chat_member.invite_link.creator.id == context.bot.id:
            logger.info(f"user joined a netwrok chat ({chat.title}) with a link created by the bot")
            await handle_events_chat_join_via_bot_link(session, context.bot, update.chat_member)


HANDLERS = (
    (ChatMemberHandler(on_chat_member_update, ChatMemberHandler.CHAT_MEMBER), Group.NORMAL),
)
