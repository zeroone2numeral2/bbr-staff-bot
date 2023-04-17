import logging
from typing import Union, Iterable

from sqlalchemy.orm import Session
from telegram import Update, ChatMemberOwner
from telegram import User as TelegramUser
from telegram import ChatMemberAdministrator
from telegram.ext import CallbackContext
from telegram.ext import filters
from telegram.ext import MessageHandler

from database.models import User, Chat
from database.queries import chat_members
import decorators
import utilities

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_new_group_chat(update: Update, context: CallbackContext, session: Session, user: User, chat: Chat):
    new_group = bool(update.message.group_chat_created)  # do not exit when we receive this update
    if update.message.new_chat_members:
        member: TelegramUser
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                new_group = True

    if not new_group:
        return

    logger.info(f"new group chat {utilities.log(update)}")

    if utilities.is_normal_group(update.effective_chat):
        logger.info("added to a normal group: leaving...")
        await update.message.reply_text(
            "I don't work in normal groups, please uprgade this chat to supergroup and add me again!",
            quote=False
        )
        await update.effective_chat.leave()
        chat.set_left()
        return

    if not utilities.is_admin(update.effective_user):
        logger.info("unauthorized: leaving...")
        await update.effective_chat.leave()
        chat.set_left()
        return

    chat.left = False  # override, it might be True if the chat was previously set

    session.commit()  # make sure to commit now, just in case something unexpected happens while saving admins

    logger.info("saving administrators...")
    # noinspection PyTypeChecker
    administrators: Iterable[Union[ChatMemberAdministrator, ChatMemberOwner]] = await update.effective_chat.get_administrators()
    chat_members.save_administrators(session, chat.chat_id, administrators)

    administrator: ChatMemberAdministrator
    for administrator in administrators:
        if administrator.user.id == context.bot.id:
            chat.set_as_administrator(administrator.can_delete_messages)


HANDLERS = (
    (MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.CHAT_CREATED, on_new_group_chat), 1),
)
