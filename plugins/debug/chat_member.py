import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, filters, CallbackQueryHandler, ChatMemberHandler

from constants import Group

logger = logging.getLogger(__name__)


async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(update.to_dict())


HANDLERS = (
    (ChatMemberHandler(on_chat_member_update, ChatMemberHandler.ANY_CHAT_MEMBER), Group.DEBUG),
)
