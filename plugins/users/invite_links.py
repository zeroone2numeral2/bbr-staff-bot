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
from database.queries import settings, events, chat_members, private_chat_messages, chats
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

    if not events_chat.can_invite_users:
        logger.warning(f"cannot generate invite links for events chat {events_chat.title} ({events_chat.chat_id})")
        sent_message = await update.message.reply_html("Mi dispiace, non posso fornirti un link d'invito per la chat. Contatta gli admin")
        private_chat_messages.save(session, sent_message)
        return

    success, chat_invite_link = await generate_invite_link(context.bot, events_chat, user)
    if not success:
        logger.warning(f"cannot generate invite links for events chat {events_chat.title} ({events_chat.chat_id}): {chat_invite_link}")
        sent_message = await update.message.reply_html(
            f"Mi dispiace, non è stato possibile generare un link d'invito (<code>{chat_invite_link}</code>). "
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
