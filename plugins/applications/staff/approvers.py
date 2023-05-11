import logging
import re
from typing import Optional, List, Union, Iterable

from sqlalchemy.orm import Session
from telegram import Update, ChatMemberAdministrator, ChatMemberOwner, ChatMember
from telegram.ext import ContextTypes, CommandHandler, filters

from database.models import User
from database.queries import users, chat_members
import decorators
import utilities
from constants import Group
from emojis import Emoji
from config import config
from ext.filters import Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_approver_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/approver {utilities.log(update)}")

    if not utilities.is_reply_to_user(update.message, not_self=True):
        await update.message.reply_text("Rispondi ad un utente (non te stesso, non bot e non anonimo)", quote=True)
        return

    target_user = update.message.reply_to_message.from_user
    mention = utilities.mention_escaped(target_user)
    user: User = users.get_safe(session, target_user, commit=True)
    if user.can_evaluate_applications:
        user.can_evaluate_applications = False
        text = f"{mention} non potrà più approvare le richieste"

    else:
        user.can_evaluate_applications = True
        text = f"{mention} abilitato all'approvazione delle richieste"

    await update.message.reply_html(text, quote=True)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_adminsapprovers_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/adminsapprovers {utilities.log(update)}")

    administrators: Iterable[Union[ChatMemberAdministrator, ChatMemberOwner, ChatMember]] = await update.effective_chat.get_administrators()

    users_mentions = []
    for administrator in administrators:
        if administrator.user.is_bot:
            continue

        user = users.get_safe(session, administrator.user)
        user.can_evaluate_applications = True
        users_mentions.append(utilities.mention_escaped(administrator.user))

    text = f"Questi utenti ora potranno accettare/rifiutare le richieste: {', '.join(users_mentions)}"
    await update.message.reply_html(text, quote=True)

    # update the admins list while we are at it
    chat_members.save_administrators(session, update.effective_chat.id, administrators, save_users=False)


HANDLERS = (
    (CommandHandler(["approver"], on_approver_command, filters=Filter.SUPERADMIN_AND_GROUP), Group.NORMAL),
    (CommandHandler(["adminsapprovers"], on_adminsapprovers_command, filters=Filter.SUPERADMIN_AND_GROUP), Group.NORMAL),
)
