import logging

from sqlalchemy.orm import Session
from telegram import Update, ChatMember, helpers
from telegram.ext import filters, PrefixHandler, ContextTypes

from database.models import UserMessage, ChatMember as DbChatMember
from database.queries import chats, user_messages, chat_members
import decorators
import utilities
from constants import COMMAND_PREFIXES

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/info {utilities.log(update)}")

    if not update.message.reply_to_message.from_user or update.message.reply_to_message.from_user.id == context.bot.id:
        await update.effective_message.reply_text("Reply to an user's message")
        return

    user_message: UserMessage = user_messages.get_user_message(session, update)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        return

    text = f"• <b>name</b>: {helpers.mention_html(user_message.user.user_id, utilities.escape_html(user_message.user.name))}\n" \
           f"• <b>username</b>: @{user_message.user.username or '-'}\n" \
           f"• <b>first seen</b>: {user_message.user.first_seen}\n" \
           f"• <b>last seen</b>: {user_message.user.last_message}\n" \
           f"• <b>started</b>: {user_message.user.started} (on: {user_message.user.started_on})\n" \
           f"• <b>stopped</b>: {user_message.user.stopped} (on: {user_message.user.stopped_on})\n" \
           f"• <b>is bot/is premium</b>: {user_message.user.is_bot}, {user_message.user.is_premium}\n" \
           f"• <b>language code (telegram)</b>: {user_message.user.language_code}\n" \
           f"• <b>selected language</b>: {user_message.user.selected_language}"

    if user_message.user.banned:
        text += f"\n• <b>banned</b>: {user_message.user.banned} (shadowban: {user_message.user.shadowban})\n" \
                f"• <b>reason</b>: {user_message.user.banned_reason}\n" \
                f"• <b>banned on</b>: {user_message.user.banned_on}"

    chat_member = chat_members.is_users_chat_member(session, user_message.user.user_id)
    if not chat_member:
        users_chat = chats.get_users_chat(session)
        if users_chat:
            chat_member_object = context.bot.get_chat_member(users_chat.chat_id, user_message.user.user_id)
            chat_member = DbChatMember.from_chat_member(users_chat.chat_id, chat_member_object)
            session.add(chat_member)
            text += f"\n• <b>is member in users chat</b>: {chat_member.status_pretty()} (last update: {chat_member.updated_on})"
    else:
        text += f"\n• <b>is member in users chat</b>: {chat_member.status_pretty()} (last update: {chat_member.updated_on})"

    text += f"\n• #id{user_message.user.user_id}"

    await update.effective_message.reply_text(text)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, 'info', on_info_command, filters.ChatType.GROUPS & filters.REPLY), 1),
)

