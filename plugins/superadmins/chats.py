import logging
import re
from typing import Optional, List, Iterable

from sqlalchemy.orm import Session
from telegram import Update, Chat as TelegramChat
from telegram.ext import ContextTypes, CommandHandler, filters

from database.models import User, Chat
from database.queries import users, chats
import decorators
import utilities
from constants import Group
from emojis import Emoji
from ext.filters import Filter, ChatFilter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/chats {utilities.log(update)}")

    chats_list: Iterable[Chat] = chats.get_core_chats(session)
    lines = []
    for chat in chats_list:
        chat_text = f"• <b>{chat.type_pretty_it()}</b>: {utilities.escape_html(chat.title)} [<code>{chat.chat_id}</code>]"
        lines.append(chat_text)

    await update.message.reply_text("\n".join(lines))


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_setchat_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User, chat: Chat):
    logger.info(f"/setchat (group) {utilities.log(update)}")

    chat_types_str = f"<code>{'</code>, <code>'.join(Chat.DESTINATION_TYPES_GROUP)}</code>"

    if not context.args or context.args[0].lower() not in Chat.DESTINATION_TYPES_GROUP:
        await update.effective_message.reply_text(f"Specificare il tipo di destinazione per questo gruppo: {chat_types_str} "
                                                  f"(es. <code>/setchat {Chat.DESTINATION_TYPES_GROUP[0]}</code>)")
        return

    destination_type = context.args[0].lower()

    if destination_type == "staff":
        chats.reset_staff_chat(session)
        session.commit()
        chat.set_as_staff_chat()

        ChatFilter.STAFF.chat_ids = {chat.chat_id}
    elif destination_type == "users":
        chats.reset_users_chat(session)
        session.commit()
        chat.set_as_users_chat()

        ChatFilter.USERS.chat_ids = {chat.chat_id}
    elif destination_type == "evaluation":
        chats.reset_evaluation_chat(session)
        session.commit()
        chat.set_as_evaluation_chat()

        ChatFilter.EVALUATION.chat_ids = {chat.chat_id}

    await update.effective_message.reply_text(f"{utilities.escape_html(chat.title)} impostata come chat {destination_type}")


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_setchat_private_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/setchat (private) {utilities.log(update)}")

    chat_types_str = f"<code>{'</code>, <code>'.join(Chat.DESTINATION_TYPES_CHANNEL)}</code>"

    if not utilities.is_reply_to_forwarded_channel_message(update.message):
        await update.message.reply_html("usa questo comando in risposta ad un messaggio inoltrato dal canale che vuoi usare")
        return

    if not context.args or context.args[0].lower() not in Chat.DESTINATION_TYPES_CHANNEL:
        await update.effective_message.reply_text(f"Specificare il tipo di destinazione per questo canale: {chat_types_str} "
                                                  f"(es. <code>/setchat {Chat.DESTINATION_TYPES_CHANNEL[0]}</code>)")
        return

    destination_type = context.args[0].lower()

    chat = chats.get_safe(session, update.message.reply_to_message.forward_from_chat, commit=True)

    if destination_type == "log":
        chats.reset_log_chat(session)
        session.commit()
        chat.set_as_log_chat()
    else:
        chats.reset_events_chat(session)
        session.commit()
        chat.set_as_events_chat()

        ChatFilter.EVENTS.chat_ids = {chat.chat_id}
        ChatFilter.EVENTS_GROUP_POST.chat_ids = {chat.chat_id}

    await update.effective_message.reply_text(f"{utilities.escape_html(chat.title)} impostata come chat {chat.type_pretty()}")


HANDLERS = (
    (CommandHandler(["chats"], on_chats_command, filters=Filter.SUPERADMIN), Group.NORMAL),
    (CommandHandler(["setchat"], on_setchat_group_command, filters=Filter.SUPERADMIN_AND_GROUP), Group.NORMAL),
    (CommandHandler(["setchat"], on_setchat_private_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
