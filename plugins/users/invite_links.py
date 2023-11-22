import logging
from typing import Optional, Tuple, Union

from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatInviteLink, \
    Bot
from telegram.error import TelegramError, BadRequest
from telegram.ext import ContextTypes, filters, CommandHandler

import decorators
import utilities
from config import config
from constants import Group, DeeplinkParam
from database.models import Chat, User, ChatMember, InviteLink, Destination
from database.queries import chat_members, private_chat_messages, chats, invite_links
from emojis import Emoji
from ext.filters import Filter

logger = logging.getLogger(__name__)


async def generate_invite_link(bot: Bot, events_chat: Chat, user_id: int) -> Tuple[bool, Union[ChatInviteLink, str]]:
    logger.info("generating invite link...")

    try:
        chat_invite_link: ChatInviteLink = await bot.create_chat_invite_link(
            events_chat.chat_id,
            member_limit=1,
            name=f"user {user_id}",
            creates_join_request=False
        )
    except (TelegramError, BadRequest) as e:
        logger.error(f"error while generating invite link for chat {events_chat.chat_id}: {e}")
        return False, str(e)

    return True, chat_invite_link


async def generate_and_send_invite_link(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat, link_destination: str, ignore_cooldown=False):
    logger.info(f"ignore cooldown: {ignore_cooldown}")

    last_unused_invite_link: Optional[InviteLink] = invite_links.get_last_unused_invite_link(
        session,
        chat.chat_id,
        update.effective_user.id,
        destination=link_destination
    )

    if last_unused_invite_link:
        logger.info(f"user laready received a link but didn't use it, id: {last_unused_invite_link.link_id} created on {last_unused_invite_link.created_on}")
        reply_markup = None
        if last_unused_invite_link.sent_to_user_via_reply_markup:
            text = f"Usa questo link generato in precedenza {Emoji.POINT_DOWN}"
            reply_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"{Emoji.UFO} unisciti a {last_unused_invite_link.chat.title}", url=last_unused_invite_link.invite_link)
            ]])
        else:
            text = f"{Emoji.UFO} Usa <a href=\"{last_unused_invite_link.invite_link}\">questo link</a> " \
                    f"generato in precedenza per unirti a {last_unused_invite_link.chat.title_escaped()}"

        sent_message = await update.message.reply_html(text, reply_markup=reply_markup)
        private_chat_messages.save(session, sent_message)
        last_unused_invite_link.extend_message_ids_to_delete([update.message.message_id, sent_message.message_id])
        return

    if not ignore_cooldown and config.settings.events_chat_deeplink_cooldown:
        logger.info(f"cooldown is set to {config.settings.events_chat_deeplink_cooldown} seconds")
        last_invite_link: Optional[InviteLink] = invite_links.get_most_recent_invite_link(
            session,
            chat.chat_id,
            update.effective_user.id,
            destination=link_destination
        )
        if last_invite_link and last_invite_link.created_on:
            # logger.info(last_invite_link.created_on.tzinfo)
            created_on_utc = utilities.naive_to_aware(last_invite_link.created_on, force_utc=True)
            seconds_diff = (utilities.now() - created_on_utc).total_seconds()
            if seconds_diff < config.settings.events_chat_deeplink_cooldown:
                logger.info(f"link requested too soon, diff: {seconds_diff} seconds")
                diff_str = utilities.elapsed_str_from_seconds(int(config.settings.events_chat_deeplink_cooldown - seconds_diff), "poco")
                sent_message = await update.message.reply_html(
                    f"Mi dispiace, è trascorso troppo poco tempo da quando hai richiesto questo link d'invito l'ultima volta. "
                    f"Riprova tra ~{diff_str}"
                )
                private_chat_messages.save(session, sent_message)
                return

    success, chat_invite_link = await generate_invite_link(context.bot, chat, update.effective_user.id)
    if not success:
        logger.warning(f"couldn't generate invite link for events chat {chat.title} ({chat.chat_id}): {chat_invite_link}")
        sent_message = await update.message.reply_html(
            f"Mi dispiace, non è stato possibile generare un link d'invito (<code>{chat_invite_link.lower()}</code>). "
            f"Contatta gli admin"
        )
        private_chat_messages.save(session, sent_message)
        return

    invite_link: InviteLink = InviteLink.from_chat_invite_link(
        chat.chat_id,
        destination=link_destination,
        chat_invite_link=chat_invite_link
    )
    session.add(invite_link)

    reply_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{Emoji.ALIEN} unisciti", url=invite_link.invite_link)
    ]])

    logger.info("sending link to user...")
    sent_message = await update.message.reply_html(
        f"{Emoji.EYE} Usa il tasto qui sotto per unirti a {chat.title_escaped()} {Emoji.POINT_DOWN}",
        reply_markup=reply_markup,
        protect_content=True
    )
    private_chat_messages.save(session, sent_message)

    invite_link.save_sent_to_user_message_data(
        sent_message,
        message_ids_to_delete=[update.message.message_id, sent_message.message_id],
        via_reply_markup=True
    )
    session.commit()


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_ban()
async def on_events_chat_invite_deeplink(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"events chat invite link deeplink {utilities.log(update)}")

    user.set_started()

    users_chat_member: Optional[ChatMember] = chat_members.get_chat_member(session, update.effective_user.id, Chat.is_users_chat)
    if not users_chat_member or not users_chat_member.is_member():
        logger.info("forbidden: user is not member of the users chat")
        return

    events_chat: Optional[Chat] = chats.get_chat(session, Chat.is_events_chat)
    if not events_chat:
        logger.warning("no events chat is set")
        return

    events_chat_chat_member = chat_members.get_chat_member(session, update.effective_user.id, Chat.is_events_chat)
    if events_chat_chat_member and events_chat_chat_member.is_member():
        logger.warning(f"user is already subscribed to {events_chat.title} ({events_chat.chat_id})")
        sent_message = await update.message.reply_html(f"{Emoji.UFO} Sei già iscritto a {utilities.escape_html(events_chat.title)}")
        private_chat_messages.save(session, sent_message)
        return

    if not events_chat.can_invite_users:
        logger.warning(f"cannot generate invite links for events chat {events_chat.title} ({events_chat.chat_id}): \"invite users\" permission missing")
        sent_message = await update.message.reply_html("Mi dispiace, non posso generare link d'invito per la chat. Contatta gli admin")
        private_chat_messages.save(session, sent_message)
        return

    await generate_and_send_invite_link(
        update=update,
        context=context,
        session=session,
        chat=events_chat,
        link_destination=Destination.EVENTS_CHAT_DEEPLINK,
        ignore_cooldown="ecil" in update.message.text
    )


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_ban()
async def on_users_chat_invite_deeplink(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"users chat invite link deeplink {utilities.log(update)}")

    user.set_started()

    users_chat: Optional[Chat] = chats.get_chat(session, Chat.is_users_chat)
    if not users_chat:
        logger.warning("no users chat is set")
        return

    if not users_chat.can_invite_users:
        logger.warning(f"cannot generate invite links for users chat {users_chat.title} ({users_chat.chat_id}): \"invite users\" permission missing")
        sent_message = await update.message.reply_html("Mi dispiace, non posso generare link d'invito per il gruppo. Contatta gli admin")
        private_chat_messages.save(session, sent_message)
        return

    user_allowed = False

    users_chat_member: Optional[ChatMember] = chat_members.get_chat_member(session, update.effective_user.id, Chat.is_users_chat)
    if not user_allowed and (users_chat_member and users_chat_member.is_member()):
        logger.info("allowed: user is member of the members chat")
        user_allowed = True

    if not user_allowed and (users_chat_member and users_chat_member.left_or_kicked()):
        logger.info("allowed: user was a member of the users chat and left, or was kicked")
        user_allowed = True

    if not user_allowed and (user.last_request and user.last_request.accepted()):
        logger.info("allowed: user's last request was accepted")
        user_allowed = True

    if not user_allowed:
        logger.info(f"forbidden: none of the conditions were met (last request was accepted/member of the users chat/left or kicked from the users chat)")
        return

    await generate_and_send_invite_link(
        update=update,
        context=context,
        session=session,
        chat=users_chat,
        link_destination=Destination.USERS_CHAT_DEEPLINK
    )


HANDLERS = (
    (CommandHandler("start", on_events_chat_invite_deeplink, filters=filters.ChatType.PRIVATE & filters.Regex(fr"{DeeplinkParam.EVENTS_CHAT_INVITE_LINK}$")), Group.NORMAL),
    (CommandHandler("ecil", on_events_chat_invite_deeplink, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler("start", on_users_chat_invite_deeplink, filters=filters.ChatType.PRIVATE & filters.Regex(fr"{DeeplinkParam.USERS_CHAT_INVITE_LINK}$")), Group.NORMAL),
)
