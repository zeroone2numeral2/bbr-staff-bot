import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, PrefixHandler
from telegram.ext import filters

from database.models import User, UserMessage
from database.queries import settings, user_messages
import decorators
import utilities
from constants import BotSettingKey, COMMAND_PREFIXES

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_revoke_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/revoke (user) {utilities.log(update)}")

    if not settings.get_or_create(session, BotSettingKey.ALLOW_USER_REVOKE).value():
        logger.info("user revoke is not allowed")
        return

    if not update.message.reply_to_message or update.message.reply_to_message.from_user.id != update.effective_user.id:
        await update.message.reply_text("⚠️ <i>please reply to the message you want to be deleted from the staff's chat</i>")
        return

    user_message: UserMessage = user_messages.get_user_message_by_id(session, update.message.reply_to_message.message_id)
    if not user_message:
        logger.warning(f"couldn't find replied-to message, message_id: {update.message.reply_to_message.message_id}")
        await update.message.reply_text(
            "⚠️ <i>can't find the message to revoke in the database</i>",
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        return

    logger.info(f"revoking message_id {user_message.forwarded_message_id} in staff chat_id {user_message.forwarded_chat_id}")
    await context.bot.delete_message(
        chat_id=user_message.forwarded_chat_id,
        message_id=user_message.forwarded_message_id
    )

    await update.message.reply_text(
        "🚮 <i>message revoked successfully: it has been deleted from the staff chat</i>",
        reply_to_message_id=update.message.reply_to_message.message_id
    )

    user_message.revoke()
    user_message.user.set_started()


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ['revoke', 'del'], on_revoke_user_command, filters.ChatType.PRIVATE), 1),
)
