import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.error import TelegramError, BadRequest
from telegram.ext import ContextTypes, CommandHandler

import decorators
import utilities
from constants import Group
from database.models import User, Chat
from database.queries import users, chats, chat_members, common
from ext.filters import ChatFilter
from plugins.applications.staff.common import can_evaluate_applications

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
async def on_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/reset {utilities.log(update)}")

    if not can_evaluate_applications(session, update.effective_user):
        logger.info("user is not allowed to use this command")
        return

    user: User = await common.get_user_instance_from_message(update, context, session)
    if not user:
        # the function will take care of sending the error message too
        return

    user.reset_evaluation()
    await update.message.reply_text(
        f"{user.mention()} ora potrà richiedere nuovamente di essere ammesso al gruppo "
        f"(eventuali richieste pendenti o rifiutate sono state dimenticate, se era bannato è stato sbannato)",
        quote=True
    )

    # unban the user so they can join again, just in case the user was removed manually before /reset was used
    only_if_banned = not utilities.get_command(update.message.text) == "resetkick"  # check whether to kick the user
    users_chat_member = chat_members.get_chat_member(session, user.user_id, Chat.is_users_chat)
    if users_chat_member:
        try:
            await context.bot.unban_chat_member(users_chat_member.chat_id, user.user_id, only_if_banned=only_if_banned)
            logger.debug("user unbanned")
        except (TelegramError, BadRequest) as e:
            logger.debug(f"error while unbanning member: {e}")

    log_chat = chats.get_chat(session, Chat.is_log_chat)
    if not log_chat:
        return

    log_text = f"<b>#RESET</b> da parte di {update.effective_user.mention_html()} • #admin{update.effective_user.id}\n\n" \
               f"{user.mention()} (#id{user.user_id}) potrà riutilizzare il bot per fare richiesta di essere aggiunt* al gruppo"

    additional_context = utilities.get_argument(
        ["resetkick", "reset"],
        update.message.text_html,
        bot_username=context.bot.username,
        remove_user_id_hashtag=True
    )
    if additional_context:
        log_text += f"\n<b>Contesto</b>: {additional_context}"

        # send the context to the user
        # sent_message = await context.bot.send_message(user.user_id, additional_context)
        # private_chat_messages.save(session, sent_message)

    await context.bot.send_message(log_chat.chat_id, log_text)


HANDLERS = (
    (CommandHandler(["reset", "resetkick"], on_reset_command, ChatFilter.EVALUATION), Group.NORMAL),
)
