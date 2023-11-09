import json
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, MessageId
from telegram.constants import ChatAction
from telegram.error import TelegramError, BadRequest
from telegram.ext import filters, ContextTypes, MessageHandler
from telegram.ext.filters import MessageFilter

from constants import Group
from database.models import UserMessage, AdminMessage, User, Chat, PrivateChatMessage
from database.queries import user_messages, admin_messages, users, private_chat_messages
import decorators
import utilities
from emojis import Emoji
from ext.filters import ChatFilter, Filter
from config import config

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True, pass_chat=True)
async def on_admin_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User, chat: Chat):
    logger.info(f"reply to a message starting by ++ {utilities.log(update)}")

    if update.message.reply_to_message.from_user.id == context.bot.id:
        await update.message.reply_text("⚠️ <i>please reply to the admin message you want "
                                        "to reply to</i>")
        return

    admin_message: AdminMessage = admin_messages.get_admin_message(session, update)
    if not admin_message:
        logger.warning(f"couldn't find replied-to admin message, "
                       f"chat_id: {update.effective_chat.id}; "
                       f"message_id: {update.message.reply_to_message.message_id}")
        await update.message.reply_text(
            "⚠️ <i>can't find the message to reply to in the database</i>",
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        return

    if chat.is_evaluation_chat and not admin_message.user_message:
        # this happens *only* when the message starting by "++" is sent in reply to an admin message that was sent
        # in reply to a "new request" message sent in this chat by the bot. In fact, that admin reply wasn't sent in reply to
        # an user message, therefore admin_message.user_message is empty because it cannot be linked to any UserMessage
        logger.info("++ was sent in reply to an admin message that was sent in reply to a \"new request\" message: ignoring")
        await update.message.reply_html(
            "<i>\"++\" non può essere usato in risposta ad un messaggio dello staff che risponde ad "
            "un messaggio di servizio che notifica l'arrivo di una nuova richiesta</i>",
            quote=True
        )
        return

    await context.bot.send_chat_action(admin_message.user_message.user_id, ChatAction.TYPING)
    # time.sleep(3)

    sent_message = await context.bot.send_message(
        chat_id=admin_message.user_message.user_id,
        text=re.sub(r"^\+\+\s*", "", update.effective_message.text_html),
        reply_to_message_id=admin_message.reply_message_id,  # reply to the admin message we previously sent in the chat
        allow_sending_without_reply=True,
        protect_content=config.settings.protected_admin_replies
    )
    private_chat_messages.save(session, sent_message)

    admin_message = AdminMessage(
        message_id=update.effective_message.id,
        chat_id=update.effective_chat.id,
        staff_user_id=update.effective_user.id,  # admin's user_id
        target_user_id=admin_message.target_user_id,
        user_message_id=admin_message.user_message.message_id,  # root user message that generated the admins' replies chain
        reply_message_id=sent_message.message_id,
        message_datetime=update.effective_message.date
    )
    session.add(admin_message)
    session.commit()  # we need to commit now because otherwise 'admin_message.user_message' would be none

    admin_message.save_message_json(sent_message)
    admin_message.user_message.add_reply()

    await update.message.reply_html(f"<i>message sent to {admin_message.target_user.mention()}</i>", quote=True)


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_bot_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"reply to a bot message {utilities.log(update)}")

    text = update.message.text or update.message.caption
    if text and text.startswith("."):
        logger.info("ignoring staff reply starting by .")
        return

    user_message: Optional[UserMessage] = None
    if chat.is_evaluation_chat and update.message.reply_to_message.text and re.search(r"^.+nuova #richiesta", update.message.reply_to_message.text):
        logger.info("reply to an user request message sent by the bot in the evaluation chat")
        # get the User object from the db based on the #id hashtag
        user_id = utilities.get_user_id_from_text(update.message.reply_to_message.text)
        user: User = users.get_or_create(session, user_id, create_if_missing=False)
        if not user:
            # return if missing
            logger.warning(f"couldn't find user {user_id} in the database")
            return

        # set this flag to true, so we know that the user's replies should be forwarded to the staff
        user.conversate_with_staff_override = True
    else:
        user_message: UserMessage = user_messages.get_user_message(session, update)
        if not user_message:
            logger.warning(f"couldn't find replied-to message, "
                           f"chat_id: {update.effective_chat.id}; "
                           f"message_id: {update.message.reply_to_message.message_id}")
            return
        user: User = user_message.user

    user: User
    try:
        await context.bot.send_chat_action(user.user_id, ChatAction.TYPING)
        # time.sleep(3)
    except (TelegramError, BadRequest) as e:
        if e.message.lower() == "forbidden: bot was blocked by the user":
            logger.warning("bot was blocked by the user")
            await update.message.reply_text(
                f"{Emoji.WARNING} <i>coudln't send the message to {user.mention()}: they blocked the bot</i>",
                quote=True
            )
            user.set_stopped()
            return
        else:
            raise e

    # if the admin message is a reply to a request message in the evaluation chat, reply to the message we sent the user
    # when we told them their request was sent to the staff
    user_chat_reply_to_message_id = None
    if user_message:
        user_chat_reply_to_message_id = user_message.message_id
    elif user.last_request:
        # the evalutation chat's reply might be a reply to a request that was already accepted/rejected...
        user_chat_reply_to_message_id = user.last_request.request_sent_message_message_id
    elif user.pending_request:
        # ...or to a pending request
        user_chat_reply_to_message_id = user.pending_request.request_sent_message_message_id

    sent_message: MessageId = await update.message.copy(
        chat_id=user.user_id,
        reply_to_message_id=user_chat_reply_to_message_id,
        allow_sending_without_reply=True,  # in case the user deleted their own message in the bot's chat
        protect_content=config.settings.protected_admin_replies
    )

    private_chat_message = PrivateChatMessage(
        message_id=sent_message.message_id,
        user_id=user.user_id,
        from_self=True,
        date=utilities.now(),
        message_json=json.dumps(sent_message.to_dict(), indent=2)
    )
    session.add(private_chat_message)

    if user_message:
        user_message.add_reply()
    session.commit()

    admin_message = AdminMessage(
        message_id=update.effective_message.id,
        chat_id=update.effective_chat.id,
        staff_user_id=update.effective_user.id,
        target_user_id=user.user_id,
        user_message_id=user_chat_reply_to_message_id,  # the message_id of the message we replied to in ther user chat
        reply_message_id=sent_message.message_id,
        message_datetime=update.effective_message.date
    )
    session.add(admin_message)

    await update.message.reply_html(f"<i>message sent to {user.mention()}</i>", quote=True)


HANDLERS = (
    (MessageHandler((ChatFilter.STAFF | ChatFilter.EVALUATION) & ~filters.UpdateType.EDITED_MESSAGE & Filter.REPLY_TOPICS_AWARE & filters.Regex(r"^\+\+\s*.+"), on_admin_message_reply), Group.NORMAL),
    (MessageHandler((ChatFilter.STAFF | ChatFilter.EVALUATION) & ~filters.UpdateType.EDITED_MESSAGE & Filter.REPLY_TO_BOT, on_bot_message_reply), Group.NORMAL),
)
