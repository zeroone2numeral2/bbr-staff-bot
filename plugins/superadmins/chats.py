import logging
from typing import Iterable

from sqlalchemy.orm import Session
from telegram import Update, KeyboardButtonRequestChat, ReplyKeyboardMarkup, \
    KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CommandHandler, MessageHandler
from telegram.ext import filters

import decorators
import utilities
from constants import Group
from database.models import User, Chat, ChatDestination
from database.queries import chats, chat_members
from emojis import Emoji
from ext.filters import Filter, ChatFilter

logger = logging.getLogger(__name__)


class RequestId:
    STAFF = 1
    USERS = 2
    EVALUATION = 3
    EVENTS = 4
    LOG = 5


REQUEST_ID_TO_DESTINATION = {
    RequestId.STAFF: ChatDestination.STAFF,
    RequestId.USERS: ChatDestination.USERS,
    RequestId.EVALUATION: ChatDestination.EVALUATION,
    RequestId.EVENTS: ChatDestination.EVENTS,
    RequestId.LOG: ChatDestination.LOG,
}


SET_CHAT_MARKUP = ReplyKeyboardMarkup([
    # bot_is_member will *NOT* force the client to show just the groups it is already member of
    # the user will be able to pick *ANY* group, and the bot will be added to the group if not already a member
    # if bot_is_member is false, the bot will not be added to the group
    # should be true just for channels
    [
        KeyboardButton(f"{Emoji.PEOPLE} staff", request_chat=KeyboardButtonRequestChat(RequestId.STAFF, chat_is_channel=False, bot_is_member=False)),
        KeyboardButton(f"{Emoji.PEOPLE} utenti", request_chat=KeyboardButtonRequestChat(RequestId.USERS, chat_is_channel=False, bot_is_member=False)),
    ],
    [
        KeyboardButton(f"{Emoji.PEOPLE} approvazioni", request_chat=KeyboardButtonRequestChat(RequestId.EVALUATION, chat_is_channel=True, bot_is_member=False)),
        KeyboardButton(f"{Emoji.ANNOUNCEMENT} log", request_chat=KeyboardButtonRequestChat(RequestId.LOG, chat_is_channel=True, bot_is_member=True))
    ],
    [
        KeyboardButton(f"{Emoji.ANNOUNCEMENT} eventi", request_chat=KeyboardButtonRequestChat(RequestId.EVENTS, chat_is_channel=True, bot_is_member=True)),
        KeyboardButton(f"{Emoji.CANCEL} annulla selezione")
    ]
], resize_keyboard=True)


@decorators.catch_exception()
@decorators.pass_session()
async def on_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/chats {utilities.log(update)}")

    chats_list: Iterable[Chat] = chats.get_core_chats(session)
    lines = []
    for chat in chats_list:
        chat_text = f"• <b>{chat.type_pretty_it()}</b>: {utilities.escape_html(chat.title)} [<code>{chat.chat_id}</code>]"
        lines.append(chat_text)

    await update.message.reply_text("\n".join(lines))


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_setchat_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"/setchat (group) {utilities.log(update)}")

    chat_types_str = f"<code>{'</code>, <code>'.join(Chat.DESTINATION_TYPES_GROUP)}</code>"

    if not context.args or context.args[0].lower() not in Chat.DESTINATION_TYPES_GROUP:
        await update.effective_message.reply_text(f"Specificare il tipo di destinazione per questo gruppo: {chat_types_str} "
                                                  f"(es. <code>/setchat {Chat.DESTINATION_TYPES_GROUP[0]}</code>)")
        return

    destination_type = context.args[0].lower()

    if destination_type == ChatDestination.STAFF:
        chats.reset_staff_chat(session)
        session.commit()
        chat.set_as_staff_chat()

        ChatFilter.STAFF.chat_ids = {chat.chat_id}
    elif destination_type == ChatDestination.USERS:
        chats.reset_users_chat(session)
        session.commit()
        chat.set_as_users_chat()

        ChatFilter.USERS.chat_ids = {chat.chat_id}
    elif destination_type == ChatDestination.EVALUATION:
        chats.reset_evaluation_chat(session)
        session.commit()
        chat.set_as_evaluation_chat()

        ChatFilter.EVALUATION.chat_ids = {chat.chat_id}

    await update.effective_message.reply_text(f"{utilities.escape_html(chat.title)} impostata come chat {destination_type}")


@decorators.catch_exception()
@decorators.pass_session()
async def on_setchat_private_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/setchat (private) {utilities.log(update)}")

    chat_types_str = f"<code>{'</code>, <code>'.join(Chat.DESTINATION_TYPES_CHANNEL)}</code>"

    if not utilities.is_reply_to_forwarded_channel_message(update.message):
        await update.message.reply_html("usa questo comando in risposta ad un messaggio inoltrato dal canale che vuoi usare")
        return

    if not context.args or context.args[0].lower() not in Chat.DESTINATION_TYPES_CHANNEL:
        await update.effective_message.reply_text(f"Specificare il tipo di destinazione per questo canale: {chat_types_str} "
                                                  f"(es. <code>/setchat {Chat.DESTINATION_TYPES_CHANNEL[0]}</code>)")
        return

    destination_type = context.args[0].lower()

    # noinspection PyUnresolvedReferences
    chat = chats.get_safe(session, update.message.reply_to_message.forward_origin.chat, commit=True)

    if destination_type == ChatDestination.LOG:
        chats.reset_log_chat(session)
        session.commit()
        chat.set_as_log_chat()
    else:
        chats.reset_events_chat(session)
        session.commit()
        chat.set_as_events_chat()

        ChatFilter.EVENTS.chat_ids = {chat.chat_id}
        ChatFilter.EVENTS_GROUP_POST.chat_ids = {chat.chat_id}

    await update.effective_message.reply_text(f"{utilities.escape_html(chat.title)} impostata come chat {chat.type_pretty()}")


@decorators.catch_exception()
async def on_setchat_new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/setchat {utilities.log(update)}")

    await update.effective_message.reply_text(
        f"Seleziona il tipo di chat che vuoi impostare, successivamente ti verrà chiesto di scegliere il gruppo/canale "
        f"da utilizzare tra le chat di cui fai parte\n"
        f"<b>Attenzione:</b> assicurati che il bot sia già parte della chat scelta",
        reply_markup=SET_CHAT_MARKUP
    )


@decorators.catch_exception()
@decorators.pass_session()
async def on_chat_shared_update(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"chat shared update {utilities.log(update)}")
    logger.info(f"{update.message.chat_shared}")

    chat_id = update.message.chat_shared.chat_id
    request_id = update.message.chat_shared.request_id
    bot_chat_member = chat_members.get_chat_member_by_id(session, context.bot.id, chat_id)
    if not bot_chat_member or not bot_chat_member.is_member():
        await update.message.reply_html(
            f"Il bot non è membro di questa chat. Selezionane un'altra usando i tasti qui sotto, oppure usa il tasto per annullare"
        )
        return

    destination_type = REQUEST_ID_TO_DESTINATION[request_id]

    if destination_type == ChatDestination.STAFF:
        chats.reset_staff_chat(session)
        session.commit()
        bot_chat_member.chat.set_as_staff_chat()

        ChatFilter.STAFF.chat_ids = {bot_chat_member.chat_id}
    elif destination_type == ChatDestination.USERS:
        chats.reset_users_chat(session)
        session.commit()
        bot_chat_member.chat.set_as_users_chat()

        ChatFilter.USERS.chat_ids = {bot_chat_member.chat_id}
    elif destination_type == ChatDestination.EVALUATION:
        chats.reset_evaluation_chat(session)
        session.commit()
        bot_chat_member.chat.set_as_evaluation_chat()

        ChatFilter.EVALUATION.chat_ids = {bot_chat_member.chat_id}
    elif destination_type == ChatDestination.EVENTS:
        chats.reset_events_chat(session)
        session.commit()
        bot_chat_member.chat.set_as_events_chat()

        ChatFilter.EVENTS.chat_ids = {bot_chat_member.chat_id}
    elif destination_type == ChatDestination.LOG:
        chats.reset_log_chat(session)
        session.commit()

        bot_chat_member.chat.set_as_log_chat()

    await update.effective_message.reply_text(
        f"{utilities.escape_html(bot_chat_member.chat.title)} impostata come {bot_chat_member.chat.type_pretty()}",
        reply_markup=ReplyKeyboardRemove()
    )


@decorators.catch_exception()
async def on_cancel_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"cancel chat selection button {utilities.log(update)}")

    await update.effective_message.reply_text(f"Okay, selezione annullata", reply_markup=ReplyKeyboardRemove())


@decorators.catch_exception()
@decorators.pass_session(pass_chat=True)
async def on_setnetworkchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, chat: Chat):
    logger.info(f"/(un)setnetworkchat {utilities.log(update)}")

    # delete as soon as possible
    await utilities.delete_messages_safe(update.effective_message)

    operation_type = "unset" if "unsetnetworkchat" in update.effective_message.text.lower() else "set"

    try:
        if operation_type == "set":
            chat.set_as_network_chat()
        else:
            chat.unset_as_network_chat()

        await context.bot.send_message(update.effective_user.id, f"{update.effective_chat.title} {operation_type} as network chat", parse_mode=None)
    except Exception as e:
        error_str = f"couldn't {operation_type} {update.effective_chat.title} ({update.effective_chat.id}) as network chat: {e}"
        logger.warning(error_str)
        await context.bot.send_message(update.effective_user.id, error_str, parse_mode=None)


HANDLERS = (
    (CommandHandler(["chats"], on_chats_command, filters=Filter.SUPERADMIN), Group.NORMAL),
    (CommandHandler(["setchatold"], on_setchat_group_command, filters=Filter.SUPERADMIN_AND_GROUP), Group.NORMAL),
    (CommandHandler(["setchatold"], on_setchat_private_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["setchat"], on_setchat_new_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["setnetworkchat", "unsetnetworkchat"], on_setnetworkchat_command, filters=Filter.SUPERADMIN & ~filters.SenderChat.ALL), Group.NORMAL),
    (MessageHandler(filters.StatusUpdate.CHAT_SHARED, on_chat_shared_update), Group.NORMAL),
    (MessageHandler(filters.Regex(rf"^{Emoji.CANCEL} annulla selezione$"), on_cancel_selection), Group.NORMAL),
)
