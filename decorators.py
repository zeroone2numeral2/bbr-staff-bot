import datetime
import logging
from functools import wraps
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy.sql import func as sql_func
# noinspection PyPackageRequirements
from telegram import Update, ChatMember
# noinspection PyPackageRequirements
from telegram.error import TimedOut, BadRequest
# noinspection PyPackageRequirements
from telegram.ext import CallbackContext

from database.base import get_session
from database.models import User, Chat
from database.queries import chats, chat_members
import utilities
from config import config

logger = logging.getLogger(__name__)


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
                    text = 'An error occurred while processing the message: <code>{}</code>'.format(utilities.escape_html(str(e)))
                    if update.callback_query:
                        await update.callback_query.message.reply_html(text, disable_web_page_preview=True)
                    else:
                        await update.effective_message.reply_html(text, disable_web_page_preview=True)

                # return ConversationHandler.END
                return

        return wrapped

    return real_decorator


def pass_session(
        pass_user=False,
        pass_chat=False,
        create_if_not_existing=True,
        rollback_on_exception=False,
        commit_on_exception=False
):
    # 'rollback_on_exception' should be false by default because we might want to commit
    # what has been added (session.add()) to the session until the exception has been raised anyway.
    # For the same reason, we might want to commit anyway when an exception happens using 'commit_on_exception'

    if all([rollback_on_exception, commit_on_exception]):
        raise ValueError("'rollback_on_exception' and 'commit_on_exception' are mutually exclusive")

    def real_decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
            # we fetch the session once per message at max, cause the decorator is run only if a message passes filters
            session: Session = get_session()

            # user: [User, None] = None
            # chat: [Chat, None] = None

            if pass_user:
                user = session.query(User).filter(User.user_id == update.effective_user.id).one_or_none()

                if not user and create_if_not_existing:
                    user = User(update.effective_user)
                    session.add(user)
                    session.commit()

                kwargs['user'] = user

            if pass_chat:
                if update.effective_chat.id > 0:
                    # raise ValueError("'pass_chat' cannot be True for updates that come from private chats")
                    logger.warning("'pass_chat' shouldn't be True for updates that come from private chats")
                else:
                    chat = session.query(Chat).filter(Chat.chat_id == update.effective_chat.id).one_or_none()

                    if not chat and create_if_not_existing:
                        chat = Chat(chat_id=update.effective_chat.id, title=update.effective_chat.title)
                        session.add(chat)
                        session.commit()

                    kwargs['chat'] = chat

            # noinspection PyBroadException
            try:
                result = await func(update, context, session=session, *args, **kwargs)
            except Exception:
                if rollback_on_exception:
                    logger.warning("exception while running an handler callback: rolling back")
                    session.rollback()

                if commit_on_exception:
                    logger.warning("exception while running an handler callback: committing")
                    session.commit()

                # raise the exception anyway, so outher decorators can catch it
                raise

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
            if not chat_members.is_staff_chat_admin(session, update.effective_user.id) and not utilities.is_admin(update.effective_user):
                logger.warning(f"{update.effective_user.id} ({update.effective_user.full_name}) not recognized as admin of {update.effective_chat.id} ({update.effective_chat.title})")
                staff_chat = chats.get_staff_chat(session)
                await update.message.reply_text(f"You're not an admin of {utilities.escape_html(staff_chat.title)}. "
                                                f"If you think this is an error, please ask a recognized admin to "
                                                f"use <code>/reloadadmins</code> in the staff chat")
                return

            result = await func(update, context, session=session, *args, **kwargs)
            return result

        return wrapped

    return real_decorator
