import logging
from typing import List

from sqlalchemy.orm import Session
from telegram import Update, Chat
from telegram.error import BadRequest
from telegram.ext import ContextTypes, MessageHandler, CommandHandler
from telegram.ext import filters

from database.models import StaffChatMessage
import decorators
import utilities
from constants import Group
from database.queries import staff_chat_messages
from ext.filters import ChatFilter, Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_down_db_instances=True)
async def on_staff_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"saving/updating staff chat message {update.effective_message.message_id} {utilities.log(update)}")
    message = update.effective_message

    staff_chat_message: StaffChatMessage = staff_chat_messages.get_or_create(session, message, commit=True)
    if message.edit_date:
        logger.debug("edited message: updating message metadata and returning")
        staff_chat_message.update_message_metadata(message)

        # We return just because there's a bug in teh API that will send to the bot and edited_message update when
        # someone reacts to an old message, without it being actually edited
        # https://t.me/BotTalk/813907
        # https://t.me/BotTalk/813909
        # https://t.me/tdlibchat/47242
        # https://t.me/tdlibchat/69794
        # This means that if we receave such an update, and a duplicate of this message was already sent to the group,
        # the bot will reply to the edited (not really) message saying it is a duplicate of that duplicate message
        # that was sent later
        # It is preferable to simply ignore edited messages: after all, in the staff chat, info messages & flyers
        # are usually not edited
        return

    # will also check the text length (and return an empty list if too short and no media)
    duplicates = staff_chat_messages.find_duplicates(session, message)

    if not duplicates:
        return

    logger.info(f"found {len(duplicates)} duplicates")
    duplicates_links = [d.message_link_html(f"{utilities.elapsed_str(d.message_date, 'poco')} fa") for d in duplicates]
    text = f"Sembra che questo messaggio sia già stato inviato {'; '.join(duplicates_links)}"
    await update.effective_message.reply_text(text, quote=True)


HANDLERS = (
    (MessageHandler(ChatFilter.STAFF & Filter.MESSAGE_OR_EDIT, on_staff_chat_message), Group.NORMAL),
)
