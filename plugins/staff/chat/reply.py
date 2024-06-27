import json
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update, MessageId, ReplyParameters, Message
from telegram.constants import ChatAction, ReactionEmoji
from telegram.error import TelegramError, BadRequest
from telegram.ext import filters, ContextTypes, MessageHandler

import decorators
import utilities
from config import config
from constants import Group
from database.models import UserMessage, AdminMessage, User, Chat, PrivateChatMessage
from database.queries import user_messages, admin_messages, users, private_chat_messages
from emojis import Emoji
from ext.filters import ChatFilter, Filter

logger = logging.getLogger(__name__)

INIT_CONVERSATION_STR = ">"


def get_protect_content_flag(chat: Chat) -> bool:
    if chat.is_staff_chat:
        return config.settings.protected_admin_replies
    elif chat.is_evaluation_chat:
        return config.settings.protected_admin_replies_evaluation

    return False


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_admin_message_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
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
            reply_parameters=ReplyParameters(message_id=update.message.reply_to_message.message_id)
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
            do_quote=True
        )
        return

    await context.bot.send_chat_action(admin_message.user_message.user_id, ChatAction.TYPING)
    # time.sleep(3)

    sent_message = await context.bot.send_message(
        chat_id=admin_message.user_message.user_id,
        text=re.sub(r"^\+\+\s*", "", update.effective_message.text_html),
        reply_parameters=ReplyParameters(
            message_id=admin_message.reply_message_id,  # reply to the admin message we previously sent in the chat
            allow_sending_without_reply=True
        ),
        protect_content=get_protect_content_flag(chat)
    )
    private_chat_messages.save(session, sent_message)
    await update.message.set_reaction(ReactionEmoji.WRITING_HAND)  # react as soon as we forward the message

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


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_bot_message_or_automatic_forward_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"reply to a bot message or to an automatic forward from linked channel {utilities.log(update)}")

    # logging
    if update.message.reply_to_message.is_automatic_forward:
        logger.info("reply to an automatic forward from linked channel")
    elif update.message.reply_to_message.from_user.is_bot:
        logger.info("reply to a message from self")

    text = update.message.text or update.message.caption
    if text and text.startswith("."):
        logger.info("ignoring staff reply starting by .")
        return

    user_message: Optional[UserMessage] = None

    # text version with the leading INIT_CONVERSATION_STR removed, which is needed to start a conversation from a request message
    text_or_caption_override = None
    text_or_caption_no_html = update.message.text or update.message.caption  # do not use the _html version

    if chat.is_evaluation_chat and text_or_caption_no_html and text_or_caption_no_html.startswith(INIT_CONVERSATION_STR) and re.search(r"^.+nuova #richiesta", update.message.reply_to_message.text):
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

        # do this only if the message starts a conversation from a request
        if update.message.text:
            text_or_caption_override = update.message.text_html.lstrip(utilities.escape_html(INIT_CONVERSATION_STR)).strip()
        elif update.message.caption:
            text_or_caption_override = update.message.caption_html.lstrip(utilities.escape_html(INIT_CONVERSATION_STR)).strip()
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
                do_quote=True
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
        logger.debug(f"we will reply to an UserMessage with message_id {user_chat_reply_to_message_id}")
    elif user.last_request:
        # the evalutation chat's reply might be a reply to a request that was already accepted/rejected...
        user_chat_reply_to_message_id = user.last_request.request_sent_message_message_id
        logger.debug(f"we will reply to a \"request sent\" message with message_id {user_chat_reply_to_message_id} (accepted/rejected request)")
    elif user.pending_request:
        # ...or to a pending request
        user_chat_reply_to_message_id = user.pending_request.request_sent_message_message_id
        logger.debug(f"we will reply to a \"request sent\" message with message_id {user_chat_reply_to_message_id} (pending request)")
    else:
        # might also check this -> 'if not user.last_request and not user.pending_request'
        # might happen after an admin uses /reset, because the bot forgets the last/pending request
        # we warn the staff
        logger.info(f"couldn't find any UserMessage/request to reply to, warning staff and returning")
        await update.message.reply_html(f"{Emoji.WARNING} <i>Impossibile inoltrare il messaggio a {user.mention()}: "
                                        f"nessuna richiesta associata all'utente (può essere che sia stato "
                                        f"eseguito un reset)</i>", do_quote=True)
        return

    # old way of forwarding messages using message.copy()
    # sent_message: MessageId = await update.message.copy(
    #     chat_id=user.user_id,
    #     reply_parameters=ReplyParameters(
    #         message_id=user_chat_reply_to_message_id,
    #         allow_sending_without_reply=True,  # in case the user deleted their own message in the bot's chat
    #     ),
    #     protect_content=get_protect_content_flag(chat)
    # )

    sent_message: Message = await utilities.copy_message(
        bot=context.bot,
        message=update.message,
        chat_id=user.user_id,
        text_or_caption_override=text_or_caption_override,
        reply_to_message_id=user_chat_reply_to_message_id,
        allow_sending_without_reply=True,  # in case the user deleted their own message in the bot's chat
        protect_content=get_protect_content_flag(chat)
    )

    # react right after we send the message: if something goes wrong after the message is forwarded,
    # the staff should know that the message has been delivered even if an exception has been raised
    logger.debug("reacting...")
    await update.message.set_reaction(ReactionEmoji.WRITING_HAND)
    await update.message.reply_to_message.set_reaction(ReactionEmoji.MAN_TECHNOLOGIST)

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


HANDLERS = (
    (MessageHandler((ChatFilter.STAFF | ChatFilter.EVALUATION) & ~filters.UpdateType.EDITED_MESSAGE & Filter.REPLY_TOPICS_AWARE & filters.Regex(r"^\+\+\s*.+"), on_admin_message_reply), Group.NORMAL),
    (MessageHandler((ChatFilter.STAFF | ChatFilter.EVALUATION) & ~filters.UpdateType.EDITED_MESSAGE & (Filter.REPLY_TO_BOT | Filter.REPLY_TO_AUTOMATIC_FORWARD), on_bot_message_or_automatic_forward_reply), Group.NORMAL),
)
