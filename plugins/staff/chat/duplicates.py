import logging
from typing import List

from sqlalchemy.orm import Session
from telegram import Update, Chat, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest
from telegram.ext import ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler
from telegram.ext import filters

from database.models import StaffChatMessage
import decorators
import utilities
from constants import Group, TempDataKey
from database.queries import staff_chat_messages
from emojis import Emoji
from ext.filters import ChatFilter, Filter

logger = logging.getLogger(__name__)

DUPLICATE_MESSAGE_REPLY_MARKUP = InlineKeyboardMarkup([[
    InlineKeyboardButton(f"{Emoji.SIGN} elimina questo messaggio", callback_data=f"deldup")
]])


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
        # https://t.me/tdlibchat/124993
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
    await update.effective_message.reply_text(text, reply_markup=DUPLICATE_MESSAGE_REPLY_MARKUP, quote=True)


@decorators.catch_exception()
async def on_delete_message_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"delete duplicate notification button {utilities.log(update)}")

    tap_key = f"deldup:{update.effective_chat.id}:{update.effective_message.message_id}"

    if TempDataKey.DELETE_DUPLICATE_MESSAGE_BUTTON_ONCE not in context.user_data:
        context.user_data[TempDataKey.DELETE_DUPLICATE_MESSAGE_BUTTON_ONCE] = {}

    if tap_key not in context.user_data[TempDataKey.DELETE_DUPLICATE_MESSAGE_BUTTON_ONCE]:
        logger.info(f"first time tap for key {tap_key}, showing alert...")
        await update.callback_query.answer(
            f"usa di nuovo il tasto per eliminare il messaggio",
            show_alert=False
        )
        context.user_data[TempDataKey.DELETE_DUPLICATE_MESSAGE_BUTTON_ONCE][tap_key] = True
        return

    context.user_data[TempDataKey.DELETE_DUPLICATE_MESSAGE_BUTTON_ONCE].pop(tap_key, None)
    await utilities.delete_messages_safe(update.effective_message)


HANDLERS = (
    (MessageHandler(ChatFilter.STAFF & Filter.MESSAGE_OR_EDIT, on_staff_chat_message), Group.NORMAL),
    (CallbackQueryHandler(on_delete_message_button, rf"deldup$"), Group.NORMAL),
)
