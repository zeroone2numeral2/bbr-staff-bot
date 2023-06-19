import logging
import re
from typing import Optional, List

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from database.models import User, Chat
from database.queries import users, chats
import decorators
import utilities
from constants import Group
from emojis import Emoji

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/reset {utilities.log(update)}")

    if not user.can_evaluate_applications and not utilities.is_superadmin(update.effective_user):
        return

    user_id_match = re.search(r"(?:#user|#id)?(?P<user_id>\d+)", update.message.text, re.I)
    if not user_id_match:
        await update.message.reply_text("impossibile rilevare l'id dell'utente")
        return

    user_id = int(user_id_match.group("user_id"))
    user: User = users.get_or_create(session, user_id, create_if_missing=False)
    if not user:
        await update.message.reply_text(f"impossibile trovare l'utente <code>{user_id}</code> nel database")
        return

    user.reset_evaluation()
    await update.message.reply_text(f"{user.mention()} ora potrà richiedere nuovamente di essere ammesso al gruppo")

    log_chat = chats.get_chat(session, Chat.is_log_chat)
    if not log_chat:
        return

    log_text = f"#RESET da parte di {update.effective_user.mention_html()} (#admin{update.effective_user.id}): " \
               f"{user.mention()} (#id{user.user_id}) potrà richiedere di essere ammesso nuovamente nel gruppo"
    await context.bot.send_message(log_chat.chat_id, log_text)


HANDLERS = (
    (CommandHandler(["reset"], on_reset_command), Group.NORMAL),
)
