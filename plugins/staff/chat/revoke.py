import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import filters, PrefixHandler, ContextTypes

from database.models import AdminMessage, User
from database.queries import admin_messages
import decorators
import utilities
from constants import COMMAND_PREFIXES, Group

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_revoke_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/revoke (admin) {utilities.log(update)}")

    if update.message.reply_to_message.from_user.id == context.bot.id:
        await update.message.reply_text("⚠️ <i>please reply to the staff message you want "
                                        "to be deleted from the user's chat with the bot</i>")
        return

    admin_message: AdminMessage = admin_messages.get_admin_message(session, update)
    if not admin_message:
        logger.warning(f"couldn't find replied-to admin message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        await update.message.reply_text(
            "⚠️ <i>can't find the message to revoke in the database</i>",
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        return

    logger.info(f"revoking message_id {admin_message.reply_message_id} in chat_id {admin_message.user_message.user.user_id}")
    await context.bot.delete_message(
        chat_id=admin_message.user_message.user.user_id,
        message_id=admin_message.reply_message_id
    )

    await update.message.reply_text(
        "🚮 <i>message revoked successfully: it has been deleted from the user's chat</i>",
        reply_to_message_id=update.message.reply_to_message.message_id
    )

    admin_message.revoke(revoked_by=update.effective_user.id)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ['revoke', 'del'], on_revoke_admin_command, filters.ChatType.GROUPS & filters.REPLY), Group.NORMAL),
)
