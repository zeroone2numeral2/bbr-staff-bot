import datetime
import logging
from functools import wraps
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.sql import func as sql_func
# noinspection PyPackageRequirements
from telegram import Update, ChatMember
# noinspection PyPackageRequirements
from telegram.error import TimedOut, BadRequest
# noinspection PyPackageRequirements
from telegram.ext import CallbackContext

from constants import TempDataKey
from database.base import get_session
from database.models import User, Chat
from database.queries import chats, chat_members, users, private_chat_messages
import utilities
from config import config
from emojis import Emoji

logger = logging.getLogger(__name__)


class DatabaseInstanceKey:
    USER = "db_user"
    CHAT = "db_chat"
    SESSION = "session"


def action(chat_action):
    def real_decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
            await context.bot.send_chat_action(update.effective_chat.id, chat_action)
            return func(update, context, *args, **kwargs)

        return wrapped

    return real_decorator


def catch_exception(silent=False, skip_not_modified_exception=False):
    def real_decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
            try:
                return await func(update, context, *args, **kwargs)
            except TimedOut:
                # what should this return when we are inside a conversation?
                logger.error('Telegram exception: TimedOut')
            except Exception as e:
                logger.error('error while running handler callback: %s', str(e), exc_info=True)

                if not silent:
                    text = f'{Emoji.BOT} Oops, something went wrong: <code>{utilities.escape_html(str(e))}</code>'
                    if update.callback_query:
                        sent_message = await update.callback_query.message.reply_html(text)
                    else:
                        sent_message = await update.effective_message.reply_html(text)

                    if sent_message.chat.id > 0:
                        # only save if we sent the message in a private chat
                        try:
                            private_chat_messages.save(get_session(), sent_message, commit=True)
                        except Exception as e:
                            logger.warning(f"error while saving \"an error occurred\" message: {e}")

                # return ConversationHandler.END
                return

        return wrapped

    return real_decorator


def pass_session(
        pass_user=False,
        pass_chat=False,
        rollback_on_exception=False,
        commit_on_exception=True,
        pass_down_db_instances=False
):
    # 'rollback_on_exception' should be false by default because we might want to commit
    # what has been added (session.add()) to the session until the exception has been raised anyway.
    # For the same reason, we might want to commit anyway when an exception happens using 'commit_on_exception'

    if all([rollback_on_exception, commit_on_exception]):
        raise ValueError("'rollback_on_exception' and 'commit_on_exception' are mutually exclusive")

    def real_decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
            session: Optional[Session] = None
            user: Optional[User] = None
            chat: Optional[Chat] = None

            if TempDataKey.DB_INSTANCES in context.chat_data:
                logger.debug(f"chat_data contains {TempDataKey.DB_INSTANCES} (session will be recycled)")
                if DatabaseInstanceKey.SESSION not in context.chat_data[TempDataKey.DB_INSTANCES]:
                    raise ValueError("session object was not passed in chat_data")
                session = context.chat_data[TempDataKey.DB_INSTANCES][DatabaseInstanceKey.SESSION]

                if DatabaseInstanceKey.USER in context.chat_data[TempDataKey.DB_INSTANCES]:
                    # user might be None
                    user = context.chat_data[TempDataKey.DB_INSTANCES][DatabaseInstanceKey.USER]
                if DatabaseInstanceKey.CHAT in context.chat_data[TempDataKey.DB_INSTANCES]:
                    # chat might be None
                    chat = context.chat_data[TempDataKey.DB_INSTANCES][DatabaseInstanceKey.CHAT]

            # we fetch the session once per message at max, because the decorator is run only if a message passes filters
            # if we are using different handlers groups, the session will be fetched once per  group unless passed down
            if not session:
                logger.debug("fetching a new session")
                session: Session = get_session()

            if not pass_down_db_instances:
                # if not asked to pass them down, we can just pop them
                context.chat_data.pop(TempDataKey.DB_INSTANCES, None)

            if pass_user and update.effective_user:
                if not user:
                    # fetch it only if not passed in chat_data
                    logger.debug("fetching User object")
                    user = users.get_safe(session, update.effective_user, commit=True)
                kwargs['user'] = user

            if pass_chat and update.effective_chat:
                if update.effective_chat.id > 0:
                    # raise ValueError("'pass_chat' cannot be True for updates that come from private chats")
                    logger.warning("'pass_chat' shouldn't be True for updates that come from private chats")
                else:
                    if not chat:
                        # fetch it only if not passed in chat_data
                        logger.debug("fetching Chat object")
                        chat = chats.get_safe(session, update.effective_chat, commit=True)
                    kwargs['chat'] = chat

            # noinspection PyBroadException
            try:
                result = await func(update, context, session=session, *args, **kwargs)
            except Exception as e:
                if rollback_on_exception:
                    logger.warning(f"exception while running an handler callback ({e}): rolling back")
                    session.rollback()

                if commit_on_exception:
                    logger.warning(f"exception while running an handler callback ({e}): committing")
                    session.commit()

                # if an exception happens, we DO NOT pass session/db instances down
                if not pass_down_db_instances:
                    context.chat_data.pop(TempDataKey.DB_INSTANCES, None)

                # raise the exception anyway, so outher decorators can catch it
                raise

            if pass_down_db_instances:
                logger.debug(f"storing db instances in chat_data")
                context.chat_data[TempDataKey.DB_INSTANCES] = {
                    DatabaseInstanceKey.SESSION: session,
                    DatabaseInstanceKey.USER: user,
                    DatabaseInstanceKey.CHAT: chat
                }

            logger.debug("committing session...")
            session.commit()

            return result

        return wrapped

    return real_decorator


def staff_admin():
    def real_decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: CallbackContext, session: Session, *args, **kwargs):
            # we fetch the session once per message at max, cause the decorator is run only if a message passes filters
            if not chat_members.is_member(session, update.effective_user.id, Chat.is_staff_chat, is_admin=True) and not utilities.is_superadmin(update.effective_user):
                logger.warning(f"{update.effective_user.id} ({update.effective_user.full_name}) not recognized as admin of {update.effective_chat.id} ({update.effective_chat.title})")
                staff_chat = chats.get_chat(session, Chat.is_staff_chat)
                await update.message.reply_text(f"You're not an admin of {utilities.escape_html(staff_chat.title)}. "
                                                f"If you think this is an error, please ask a recognized admin to "
                                                f"use <code>/reloadadmins</code> in the staff chat")
                return

            result = await func(update, context, session=session, *args, **kwargs)
            return result

        return wrapped

    return real_decorator
