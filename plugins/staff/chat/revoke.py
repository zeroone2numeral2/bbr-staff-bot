import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import filters, ContextTypes, CommandHandler

import decorators
import utilities
from constants import Group
from database.models import AdminMessage
from database.queries import admin_messages
from emojis import Emoji
from ext.filters import ChatFilter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
async def on_revoke_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/revoke (admin) {utilities.log(update)}")

    if update.message.reply_to_message.from_user.id == context.bot.id:
        # do not accept replies to a bot's message
        await update.message.reply_text(f"{Emoji.WARNING} <i>please reply to the staff message you want "
                                        "to be deleted from the user's chat with the bot</i>")
        return

    admin_message: AdminMessage = admin_messages.get_admin_message(session, update)
    if not admin_message:
        logger.warning(f"couldn't find replied-to admin message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        await update.message.reply_text(
            f"{Emoji.WARNING} <i>cannot find the message to revoke in the database</i>",
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        return

    logger.info(f"revoking message_id {admin_message.reply_message_id} in chat_id {admin_message.target_user_id}")
    success = await utilities.delete_messages_by_id_safe(
        context.bot,
        chat_id=admin_message.target_user_id,
        message_ids=admin_message.reply_message_id
    )
    logger.info(f"success: {success}")

    await update.message.reply_text(
        f"{Emoji.TRASH} <i>message revoked successfully: it has been deleted from {admin_message.target_user.mention()}'s chat</i>",
        reply_to_message_id=update.message.reply_to_message.message_id
    )

    admin_message.revoke(revoked_by=update.effective_user.id)


HANDLERS = (
    (CommandHandler(["revoke", "rev", "d"], on_revoke_admin_command, (ChatFilter.STAFF | ChatFilter.EVALUATION) & filters.REPLY), Group.NORMAL),
    # (CommandHandler("start", on_revoke_staff_deeplink, filters=filters.ChatType.PRIVATE & filters.Regex(fr"{DeeplinkParam.REVOKE_STAFF_MESSAGE}$")), Group.NORMAL),
)
