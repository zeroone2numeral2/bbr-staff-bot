import datetime
import json
import logging
from typing import Optional, List, Tuple, Union

import telegram.constants
from sqlalchemy import true, false, null
from sqlalchemy.orm import Session
from telegram import Update, Message, InlineKeyboardMarkup, InlineKeyboardButton, Chat as TelegramChat, ChatInviteLink, \
    Bot
from telegram.error import TelegramError, BadRequest
from telegram.ext import ContextTypes, filters, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler
from telegram.constants import MessageLimit

from emojis import Emoji, Flag
from ext.filters import Filter
from database.models import Chat, Event, User, BotSetting, EventType, ChatMember, InviteLink, Destination
from database.queries import settings, events, chat_members, private_chat_messages, chats, invite_links
import decorators
import utilities
from constants import Group, DeeplinkParam
from config import config

logger = logging.getLogger(__name__)


async def generate_invite_link(bot: Bot, events_chat: Chat, user: User) -> Tuple[bool, Union[ChatInviteLink, str]]:
    logger.info("generating invite link...")

    try:
        chat_invite_link: ChatInviteLink = await bot.create_chat_invite_link(
            events_chat.chat_id,
            member_limit=1,
            name=f"user {user.user_id}",
            creates_join_request=False
        )
    except (TelegramError, BadRequest) as e:
        logger.error(f"error while generating invite link for chat {events_chat.chat_id}: {e}")
        return False, str(e)

    return True, chat_invite_link


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_ban()
async def on_events_chat_invite_deeplink(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"events chat invite link deeplink {utilities.log(update)}")

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
        logger.warning(f"cannot generate invite links for events chat {events_chat.title} ({events_chat.chat_id})")
        sent_message = await update.message.reply_html("Mi dispiace, non posso fornirti un link d'invito per la chat. Contatta gli admin")
        private_chat_messages.save(session, sent_message)
        return

    last_unused_invite_link: Optional[InviteLink] = invite_links.get_last_unused_invite_link(session, events_chat.chat_id, update.effective_user.id)
    if last_unused_invite_link:
        logger.info(f"user laready received a link but didn't use it, id: {last_unused_invite_link.link_id} created on {last_unused_invite_link.created_on}")
        try:
            sent_message = await update.message.reply_html(
                "^ usa il link d'invito che hai ricevuto in precedenza",
                reply_to_message_id=last_unused_invite_link.sent_to_user_message_id,
                allow_sending_without_reply=False
            )
            private_chat_messages.save(session, sent_message)
            last_unused_invite_link.extend_message_ids_to_delete([update.message.message_id, sent_message.message_id])
            return
        except (BadRequest, TelegramError) as e:
            last_unused_invite_link.sent_to_user_link_removed = True
            logger.error(f"error while trying to reply to a previously sent invite link: {e}")
            logger.info("we will generate a new one")

    if config.settings.events_chat_deeplink_cooldown:
        logger.info(f"cooldown is set to {config.settings.events_chat_deeplink_cooldown} seconds")
        last_invite_link: Optional[InviteLink] = invite_links.get_most_recent_invite_link(session, events_chat.chat_id, update.effective_user.id)
        if last_invite_link and last_invite_link.created_on:
            # logger.info(last_invite_link.created_on.tzinfo)
            created_on_utc = utilities.naive_to_aware(last_invite_link.created_on, force_utc=True)
            seconds_diff = (utilities.now() - created_on_utc).total_seconds()
            if seconds_diff < config.settings.events_chat_deeplink_cooldown:
                logger.info(f"link requested too soon, diff: {seconds_diff} seconds")
                sent_message = await update.message.reply_html(
                    f"Mi dispiace, è trascorso troppo poco tempo da quando hai richiesto questo link d'invito l'ultima volta. "
                    f"Riprova tra {int(config.settings.events_chat_deeplink_cooldown - seconds_diff)} secondi"
                )
                private_chat_messages.save(session, sent_message)
                return

    success, chat_invite_link = await generate_invite_link(context.bot, events_chat, user)
    if not success:
        logger.warning(f"couldn't generate invite link for events chat {events_chat.title} ({events_chat.chat_id}): {chat_invite_link}")
        sent_message = await update.message.reply_html(
            f"Mi dispiace, non è stato possibile generare un link d'invito (<code>{chat_invite_link.lower()}</code>). "
            f"Contatta gli admin"
        )
        private_chat_messages.save(session, sent_message)
        return

    invite_link: InviteLink = InviteLink.from_chat_invite_link(
        events_chat.chat_id,
        destination=Destination.EVENTS_CHAT_DEEPLINK,
        chat_invite_link=chat_invite_link
    )
    session.add(invite_link)

    reply_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{Emoji.ALIEN} unisciti", url=invite_link.invite_link)
    ]])

    logger.info("sending link to user...")
    sent_message = await update.message.reply_html(
        f"{Emoji.EYE} Usa il tasto qui sotto per unirti a {utilities.escape_html(events_chat.title)}:",
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


HANDLERS = (
    (CommandHandler("start", on_events_chat_invite_deeplink, filters=filters.ChatType.PRIVATE & filters.Regex(fr"{DeeplinkParam.EVENTS_CHAT_INVITE_LINK}$")), Group.NORMAL),
)