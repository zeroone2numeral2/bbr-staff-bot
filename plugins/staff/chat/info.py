import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import decorators
import utilities
from constants import COMMAND_PREFIXES, Group
from database.models import ChatMember as DbChatMember, Chat, User
from database.queries import chats, chat_members, common
from ext.filters import ChatFilter, Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/info {utilities.log(update)}")

    user: User = await common.get_user_instance_from_message(update, context, session)
    if not user:
        return

    text = f"• <b>name</b>: {user.mention()}\n" \
           f"• <b>username</b>: @{user.username or '-'}\n" \
           f"• <b>first seen</b>: {utilities.format_datetime(user.first_seen)}\n" \
           f"• <b>last message to staff</b>: {utilities.format_datetime(user.last_message)}\n" \
           f"• <b>started</b>: {str(user.started).lower()} (on: {utilities.format_datetime(user.started_on)})\n" \
           f"• <b>stopped</b>: {str(user.stopped).lower()} (on: {utilities.format_datetime(user.stopped_on)})\n" \
           f"• <b>language code (telegram/selected)</b>: {user.language_code or '-'}/{user.selected_language or '-'}"

    if user.banned:
        text += f"\n• <b>banned</b>: {str(user.banned).lower()} (shadowban: {str(user.shadowban).lower()})\n" \
                f"• <b>reason</b>: {user.banned_reason or '-'}\n" \
                f"• <b>banned on</b>: {utilities.format_datetime(user.banned_on)}"

    chat_member = chat_members.get_chat_member(session, user.user_id, Chat.is_users_chat)
    if not chat_member:
        users_chat = chats.get_chat(session, Chat.is_users_chat)
        chat_member_object = await context.bot.get_chat_member(users_chat.chat_id, user.user_id)
        chat_member = DbChatMember.from_chat_member(users_chat.chat_id, chat_member_object)
        session.add(chat_member)
    text += f"\n• <b>status in users chat</b>: {chat_member.status_pretty()} (last update: {utilities.format_datetime(chat_member.updated_on)})"

    if user.pending_request_id:
        text += f"\n• <b>user has a pending request</b>, created on " \
                f"{utilities.format_datetime(user.pending_request.created_on)} and updated on " \
                f"{utilities.format_datetime(user.pending_request.updated_on)}"
    elif user.last_request_id:
        text += f"\n• <b>user has a completed request with result</b> <code>{user.last_request.status_pretty()}</code>, created on " \
                f"{utilities.format_datetime(user.last_request.created_on)} and updated on " \
                f"{utilities.format_datetime(user.last_request.updated_on)}"

    text += f"\n• #id{user.user_id}"

    await update.effective_message.reply_text(text, quote=True)


@decorators.catch_exception()
@decorators.pass_session()
async def on_userchats_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/userchats {utilities.log(update)}")

    user = await common.get_user_instance_from_message(update, context, session)
    if not user:
        return

    user_chat_members = chat_members.get_user_chat_members(session, user.user_id)
    chats_strings = []
    chat_member: DbChatMember
    for chat_member in user_chat_members:
        text = f"• <b>{utilities.escape_html(chat_member.chat.title)}</b> [<code>{chat_member.chat.chat_id}</code>]: " \
               f"<i>{chat_member.status_pretty()}</i>"

        if not chat_member.is_member() and chat_member.has_been_member:
            text = f"{text}<i>, but has been member in the past</i>"

        text = f"{text}  (last update: {utilities.format_datetime(chat_member.updated_on, '-')})"
        chats_strings.append(text)

    if not chats_strings:
        await update.message.reply_text("-")
        return

    text = "\n".join(chats_strings)
    await update.message.reply_html(text)


HANDLERS = (
    (CommandHandler('info', on_info_command, Filter.SUPERADMIN_AND_PRIVATE | ChatFilter.STAFF | ChatFilter.EVALUATION), Group.NORMAL),
    (CommandHandler('userchats', on_userchats_command, Filter.SUPERADMIN_AND_PRIVATE | ChatFilter.STAFF | ChatFilter.EVALUATION), Group.NORMAL),
)

