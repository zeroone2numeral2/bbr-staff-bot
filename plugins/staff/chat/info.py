import logging
import re

from sqlalchemy.orm import Session
from telegram import Update, helpers
from telegram.ext import filters, PrefixHandler, ContextTypes

from database.models import UserMessage, ChatMember as DbChatMember, Chat, User
from database.queries import chats, user_messages, chat_members, users
import decorators
import utilities
from constants import COMMAND_PREFIXES, Group
from ext.filters import ChatFilter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/info {utilities.log(update)}")

    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        user_message: UserMessage = user_messages.get_user_message(session, update)
        if not user_message:
            logger.warning(f"couldn't find replied-to message, "
                           f"chat_id: {update.effective_chat.id}; "
                           f"message_id: {update.message.reply_to_message.message_id}")
            await update.message.reply_text("no data saved for the replied-to message :(")
            return
        user: User = user_message.user
    else:
        user_id_match = re.search(r"(?:#user|#id)?(?P<user_id>\d+)", update.message.text, re.I)
        if not user_id_match:
            await update.message.reply_text("can't detect the user's id, reply to one of their forwarded message or include its id after the command")
            return

        user_id = int(user_id_match.group("user_id"))
        user: User = users.get_or_create(session, user_id, create_if_missing=False)
        if not user:
            await update.message.reply_text(f"can't find user <code>{user_id}</code> in the database")
            return

    text = f"• <b>name</b>: {user.mention()}\n" \
           f"• <b>username</b>: @{user.username or '-'}\n" \
           f"• <b>first seen</b>: {user.first_seen or '-'}\n" \
           f"• <b>last seen</b>: {user.last_message or '-'}\n" \
           f"• <b>started</b>: {user.started} (on: {user.started_on or '-'})\n" \
           f"• <b>stopped</b>: {user.stopped} (on: {user.stopped_on or '-'})\n" \
           f"• <b>is bot/is premium</b>: {user.is_bot}, {user.is_premium}\n" \
           f"• <b>language code (telegram)</b>: {user.language_code or '-'}\n" \
           f"• <b>selected language</b>: {user.selected_language or '-'}"

    if user.banned:
        text += f"\n• <b>banned</b>: {user.banned} (shadowban: {user.shadowban})\n" \
                f"• <b>reason</b>: {user.banned_reason}\n" \
                f"• <b>banned on</b>: {user.banned_on}"

    chat_member = chat_members.is_member(session, user.user_id, Chat.is_users_chat)
    if not chat_member:
        users_chat = chats.get_chat(session, Chat.is_users_chat)
        if users_chat:
            chat_member_object = context.bot.get_chat_member(users_chat.chat_id, user.user_id)
            chat_member = DbChatMember.from_chat_member(users_chat.chat_id, chat_member_object)
            session.add(chat_member)
            text += f"\n• <b>membership status in users chat</b>: {chat_member.status_pretty()} (last update: {chat_member.updated_on})"
    else:
        text += f"\n• <b>membership status in users chat</b>: {chat_member.status_pretty()} (last update: {chat_member.updated_on})"

    text += f"\n• #id{user.user_id}"

    await update.effective_message.reply_text(text)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, 'info', on_info_command, ChatFilter.STAFF), Group.NORMAL),
)

