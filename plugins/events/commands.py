import json
import logging
from pathlib import Path
from typing import Optional, List, Union

from sqlalchemy import false
from sqlalchemy.orm import Session
from telegram import Update, Message, Chat as TelegramChat, MessageId, MessageOriginChannel, ReplyParameters, \
    InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import MessageType, MessageLimit
from telegram.error import TelegramError, BadRequest
from telegram.ext import ContextTypes, filters, CommandHandler, CallbackContext, MessageHandler, CallbackQueryHandler

import decorators
import utilities
from constants import Group, TempDataKey
from database.models import Event, User, DeletionReason, DELETION_REASON_DESC, ChannelComment
from database.queries import events, private_chat_messages
from ext.filters import Filter, ChatFilter
from plugins.events.common import (
    parse_message_entities,
    parse_message_text,
    drop_events_cache,
    add_event_message_metadata,
    get_all_events_strings_from_db_group_by,
    send_events_messages,
    format_event_string,
    FILTER_DESCRIPTION,
    ORDER_BY_DESCRIPTION, GROUP_BY_DESCRIPTION, EventFormatting, backup_event_media
)
from config import config

logger = logging.getLogger(__name__)


class EventMessageLinkAction:
    GET_POST = "getpost"
    GET_JSON = "getjson"
    GET_MEDIA_PATHS = "getmediapaths"
    RESTORE = "restore"
    DELETE = "delete"
    DELETE_DUPLICATE = "delduplicate"
    DELETE_MESSAGE_DELETED = "deldeleted"
    DELETE_NOT_A_PARTY = "delnotaparty"
    DELETE_OTHER = "delother"


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/events {utilities.log(update)}")

    args = context.args if context.args else []
    all_events_strings = get_all_events_strings_from_db_group_by(session, args)

    # logger.debug(f"result: {len(messages_to_send)} messages, {len(text_lines)} lines")

    protect_content = not utilities.is_superadmin(update.effective_user)
    await send_events_messages(update.message, all_events_strings, protect_content)


@decorators.catch_exception()
async def on_drop_events_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/dropeventscache {utilities.log(update)}")

    drop_events_cache(context)
    await update.message.reply_text("cache dropped")


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.check_ban()
async def on_invalid_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/invalidevents {utilities.log(update)}")

    events_list: List[Event] = events.get_events(
        session,
        filters=[Event.soon == false()],
        order_by=[Event.message_id]
    )
    all_events_strings = []
    total_entities_count = 0
    formatting = EventFormatting(use_message_date=True)
    for i, event in enumerate(events_list):
        if event.is_valid():
            continue

        text_line, event_entities_count = format_event_string(event, formatting)
        all_events_strings.append(text_line)
        total_entities_count += event_entities_count  # not used yet, find something to do with this

    protect_content = not utilities.is_superadmin(update.effective_user)
    sent_messages = await send_events_messages(update.message, all_events_strings, protect_content)
    private_chat_messages.save(session, sent_messages)


@decorators.catch_exception()
@decorators.pass_session()
async def on_parse_events_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/parseevents {utilities.log(update)}")

    events_list: List[Event] = events.get_all_events(session)
    events_count = 0
    for i, event in enumerate(events_list):
        events_count = i + 1
        logger.debug(f"{events_count}. {event}")
        parse_message_text(event.message_text, event)

        if not event.message_json:
            continue

        message_dict = json.loads(event.message_json)
        message = Message.de_json(message_dict, context.bot)
        parse_message_entities(message, event)

    await update.message.reply_text(f"parsed {events_count} db entries")


async def event_from_link(update_or_message: Union[Update, Message], context: CallbackContext, session: Session) -> Optional[Event]:
    if isinstance(update_or_message, Update):
        message: Message = update_or_message.effective_message
    elif isinstance(update_or_message, Message):
        message: Message = update_or_message
    else:
        raise ValueError(f"'update_or_message' must be of type Update or Message")

    message_link = context.args[0] if context.args else message.text
    chat_id, message_id = utilities.unpack_message_link(message_link)
    if not chat_id:
        logger.debug("invalid event link")
        await message.reply_text("Il link utilizzato non è valido")
        return

    if isinstance(chat_id, str):
        logger.debug("public chat message link")
        await message.reply_text("Questo comando non funziona con chat pubbliche (che hanno uno username)")
        return

    event_ids_str = f"<code>{chat_id}</code>/<code>{message_id}</code>"

    event: Event = events.get_or_create(session, chat_id, message_id, create_if_missing=False)
    if not event:
        logger.debug("no event saved for this message link")
        await message.reply_text(f"Nessuna festa salvata per <a href=\"{message_link}\">"
                                 f"questo messaggio</a> ({event_ids_str})")
        return

    return event


def get_event_message_link_reply_markup(event: Event):
    keyboard = [[
        InlineKeyboardButton(f"vedi post", callback_data=f"msglink:{EventMessageLinkAction.GET_POST}:{event.chat_id}:{event.message_id}"),
        InlineKeyboardButton(f"json", callback_data=f"msglink:{EventMessageLinkAction.GET_JSON}:{event.chat_id}:{event.message_id}")
    ]]
    if event.media_file_paths:
        keyboard[0].append(InlineKeyboardButton(f"media", callback_data=f"msglink:{EventMessageLinkAction.GET_MEDIA_PATHS}:{event.chat_id}:{event.message_id}"))

    if event.deleted:
        keyboard[0].append(InlineKeyboardButton(f"ripristina", callback_data=f"msglink:{EventMessageLinkAction.RESTORE}:{event.chat_id}:{event.message_id}"))
    else:
        keyboard.append([
            InlineKeyboardButton(f"elimina", callback_data=f"msglink:{EventMessageLinkAction.DELETE}:{event.chat_id}:{event.message_id}"),
            InlineKeyboardButton(f"elimina (duplicato)", callback_data=f"msglink:{EventMessageLinkAction.DELETE_DUPLICATE}:{event.chat_id}:{event.message_id}")
        ])

    return InlineKeyboardMarkup(keyboard)


def get_delete_event_options_reply_markup(chat_id: int, message_id: int):
    keyboard = [
        [InlineKeyboardButton(f"festa duplicata", callback_data=f"delopt:{EventMessageLinkAction.DELETE_DUPLICATE}:{chat_id}:{message_id}")],
        [InlineKeyboardButton(f"messaggio eliminato", callback_data=f"delopt:{EventMessageLinkAction.DELETE_MESSAGE_DELETED}:{chat_id}:{message_id}")],
        [InlineKeyboardButton(f"non una festa/evento", callback_data=f"delopt:{EventMessageLinkAction.DELETE_NOT_A_PARTY}:{chat_id}:{message_id}")],
        [InlineKeyboardButton(f"altro", callback_data=f"delopt:{EventMessageLinkAction.DELETE_OTHER}:{chat_id}:{message_id}")],
        [InlineKeyboardButton(f"➜ indietro", callback_data=f"delopt:back:{chat_id}:{message_id}")],
    ]

    return InlineKeyboardMarkup(keyboard)


def get_event_message_link_text(event: Event):
    event_str, _ = format_event_string(event)

    is_valid_str = ""
    if event.deleted:
        reason = DELETION_REASON_DESC.get(event.deleted_reason, DELETION_REASON_DESC[DeletionReason.OTHER])
        is_valid_str = f"Questo messaggio non appare in radar/nell'elenco delle feste perchè l'evento è stato eliminato a mano (motivo: {reason})\n\n"
    elif not event.is_valid():
        is_valid_str = "Questo messaggio non appare in radar/nell'elenco delle feste perchè le date non sono valide, e non c'è hashtag #soon o equivalente\n\n"

    text = f"{event_str}\n\n{is_valid_str}<i>Scegli cosa fare:</i>"

    return text


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_event_chat_message_link(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"event chat message link {utilities.log(update)}")

    event: Event = await event_from_link(update, context, session)
    if not event:
        # event_from_link() will also answer the user
        return

    text = get_event_message_link_text(event)
    reply_markup = get_event_message_link_reply_markup(event)
    await update.message.reply_html(text, reply_markup=reply_markup, do_quote=True)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_postactions_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/postactions {utilities.log(update)}")

    if not update.message.reply_to_message:
        await update.message.reply_html(f"Usa il comando in risposta ad un messaggio che contiene un link t.me")
        return

    event: Event = await event_from_link(update.message.reply_to_message, context, session)
    if not event:
        # event_from_link() will also answer the user
        return

    text = get_event_message_link_text(event)
    reply_markup = get_event_message_link_reply_markup(event)
    await update.message.reply_html(text, reply_markup=reply_markup, do_quote=True)


@decorators.catch_exception()
@decorators.pass_session()
async def on_event_link_action_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"message link action {utilities.log(update)}")
    action = context.matches[0].group("action")
    chat_id = int(context.matches[0].group("chat_id"))
    message_id = int(context.matches[0].group("message_id"))

    if action == EventMessageLinkAction.DELETE:
        # generic "delete": show more options
        reply_markup = get_delete_event_options_reply_markup(chat_id, message_id)
        await update.callback_query.edit_message_reply_markup(reply_markup)
        return

    event = events.get_or_create(session, chat_id, message_id, create_if_missing=False)
    if not event:
        logger.warning(f"cannot find event: chat_id: {chat_id}, message_id: {message_id}")
        await update.callback_query.answer(f"Impossibile trovare evento (chat id: {chat_id}, message id: {message_id})")
        await update.effective_message.edit_reply_markup(reply_markup=None)
        return

    logger.info(f"action selected: {action}")

    if action == EventMessageLinkAction.RESTORE:
        event.restore()

        context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True
        drop_events_cache(context)

        await update.callback_query.answer("evento ripristinato")
    elif action == EventMessageLinkAction.DELETE_DUPLICATE:
        event.delete(DeletionReason.DUPLICATE)

        context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True
        drop_events_cache(context)

        await update.callback_query.answer("evento eliminato (duplicato)")
    elif action == EventMessageLinkAction.GET_MEDIA_PATHS:
        await update.callback_query.answer("invio elenco paths di media salvati per la festa...")

        text = ""
        for file_path in event.get_media_file_paths():
            text += f"<code>{utilities.escape_html(file_path)}</code>\n"

        text += "\nUsa <code>/getpath </code>seguito dall'indirizzo del file per inviarlo"

        await update.effective_message.reply_html(text)
        return  # no need to do edit the message
    elif action == EventMessageLinkAction.GET_JSON:
        await update.callback_query.answer("invio json evento...")

        instance_str = json.dumps(
            event.as_dict(pop_keys=["message_json"]),
            default=lambda o: str(o),
            indent=2,
            sort_keys=True
        )
        html_text = f"<pre><code class=\"language-json\">{utilities.escape(instance_str)}</code></pre>"
        if len(html_text) < MessageLimit.MAX_TEXT_LENGTH:
            await update.effective_message.reply_html(html_text)
        else:
            file_name = f"event_{event.chat_id}_{event.message_id}.json"
            file_path = Path("tmp_data") / file_name
            with open(file_path, "w+") as f:
                f.write(f"{instance_str}\n")

            await update.effective_message.reply_document(file_path, filename=file_name)
            file_path.unlink(missing_ok=True)  # deletes the file

        return  # no need to do edit the message
    elif action == EventMessageLinkAction.GET_POST:
        await update.callback_query.answer("invio evento...")

        if not event.media_file_id:
            await update.effective_message.reply_html(f"{event.message_text}")
        else:
            # if no media_type, assume photo
            media_type = event.media_type or MessageType.PHOTO
            await utilities.reply_media(
                message=update.effective_message,
                media_type=media_type,
                file_id=event.media_file_id,
                caption=event.message_text
            )

    text = get_event_message_link_text(event)
    reply_markup = get_event_message_link_reply_markup(event)
    try:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" not in e.message.lower():
            raise e
        else:
            logger.debug("message is not modified")


@decorators.catch_exception()
@decorators.pass_session()
async def on_delete_option_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"delete event option button {utilities.log(update)}")
    action = context.matches[0].group("action")
    chat_id = int(context.matches[0].group("chat_id"))
    message_id = int(context.matches[0].group("message_id"))

    event = events.get_or_create(session, chat_id, message_id, create_if_missing=False)
    if not event:
        logger.warning(f"cannot find event: chat_id: {chat_id}, message_id: {message_id}")
        await update.callback_query.answer(f"Impossibile trovare evento (chat id: {chat_id}, message id: {message_id})")
        await update.effective_message.edit_reply_markup(reply_markup=None)
        return

    if action in (EventMessageLinkAction.DELETE_DUPLICATE, EventMessageLinkAction.DELETE_MESSAGE_DELETED, EventMessageLinkAction.DELETE_NOT_A_PARTY, EventMessageLinkAction.DELETE_OTHER):
        logger.info("dropping events cache...")
        context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True
        drop_events_cache(context)

    logger.info(f"delete options, selected action: {action}")

    deletion_info = "I messaggi eliminati non appaiono nella lista delle feste fissata, e nel radar"
    if action == EventMessageLinkAction.DELETE_DUPLICATE:
        event.delete(DeletionReason.DUPLICATE)
        await update.callback_query.answer(f"Eliminato: duplicato\n\n{deletion_info}", show_alert=True)
    elif action == EventMessageLinkAction.DELETE_MESSAGE_DELETED:
        event.delete(DeletionReason.MESSAGE_DELETED)
        await update.callback_query.answer(f"Eliminato: il messaggio nel canale è stato eliminato\n\n{deletion_info}", show_alert=True)
    elif action == EventMessageLinkAction.DELETE_NOT_A_PARTY:
        event.delete(DeletionReason.NOT_A_PARTY)
        await update.callback_query.answer(f"Eliminato: il messaggio non si riferiva ad una festa\n\n{deletion_info}", show_alert=True)
    elif action == EventMessageLinkAction.DELETE_OTHER:
        event.delete(DeletionReason.OTHER)
        await update.callback_query.answer(f"Eliminato\n\n{deletion_info}", show_alert=True)

    session.commit()

    text = get_event_message_link_text(event)
    reply_markup = get_event_message_link_reply_markup(event)
    try:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" not in e.message.lower():
            raise e
        else:
            logger.debug("message is not modified")


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_reparse_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/reparse {utilities.log(update)}")

    # two ways for this command to work:
    # 1. it can be used with no argument as an answer to a forwarded channel message, in this case we will
    #    try to get the event from the forwarded message and reparse it
    # 2. it can be used in reply to a message with an argument, that is, the message link of the Event object
    #    this is particularly useful when we need to reparse an event in a channel where content is protected,
    #    so we send to the bot the new "dummy" text and reply to that text with the link of the event to update

    if context.args:
        logger.info("args were passed: get the event from the message link")
        # if the command argument is wrong or no event is found, this function will also reply to the user
        event: Optional[Event] = await event_from_link(update, context, session)
        if not event:
            # event_from_link() already replied to the user, just return
            return
    else:
        if not update.message.reply_to_message.forward_origin or not isinstance(update.message.reply_to_message.forward_origin, MessageOriginChannel):
            await update.message.reply_html(
                "Rispondi ad un messaggi inoltrato da un canale, oppure ad un messaggio di testo seguito dal link "
                "al messaggio dell'evento"
            )
            return

        chat_id = update.message.reply_to_message.forward_origin.chat.id
        message_id = update.message.reply_to_message.forward_origin.message_id

        event: Event = events.get_or_create(session, chat_id, message_id)
        if not event:
            await update.message.reply_html(f"No event for <code>{chat_id}</code>/<code>{message_id}</code>")
            return

    message_to_parse: Message = update.message.reply_to_message
    add_event_message_metadata(message_to_parse, event, reparse=True)
    parse_message_entities(message_to_parse, event)
    parse_message_text(message_to_parse.text or message_to_parse.caption, event)

    logger.info(f"re-parsed event: {event}")

    logger.info("setting flag to signal that the parties message list shoudl be updated...")
    context.bot_data[TempDataKey.UPDATE_PARTIES_MESSAGE] = True

    event_str, _ = format_event_string(event)
    await update.effective_message.reply_text(f"{event_str}\n\n^event re-parsed")

    logger.info("dropping events cache...")
    drop_events_cache(context)

    session.commit()


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_getfilters_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/getfilters {utilities.log(update)}")

    text = "<b>Filtri disponibili:</b>"
    for filter_key, description in FILTER_DESCRIPTION.items():
        text += f"\n<code>{filter_key}</code> ➜ {description}"

    text += "\n\n<b>Ordinamento disponibili:</b>"
    for filter_key, description in ORDER_BY_DESCRIPTION.items():
        text += f"\n<code>{filter_key}</code> ➜ {description}"

    text += "\n\n<b>Raggruppamenti disponibili:</b>"
    for filter_key, description in GROUP_BY_DESCRIPTION.items():
        text += f"\n<code>{filter_key}</code> ➜ {description}"

    text += (f"\n\nUsa <code>/feste [elenco filtri separati da uno spazio]</code> per filtrare le feste\n"
             f"E' possibile combinare più filtri, i filtri per l'ordinamento verranno applicati nell'ordine in cui "
             f"sono elencati\n\n"
             f"Ad esempio, \"<code>/feste ni or od</code>\" restituirà tutte le feste all'estero (\"ni\"), "
             f"ordinate prima per stato/regione (\"or\") e poi per data (\"od\")")
    await update.message.reply_html(text)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_getpath_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/getpath {utilities.log(update)}")

    command = utilities.get_command(update.message.text)
    file_path = utilities.get_argument(command, update.message.text, context.bot.username)
    if not file_path:
        await update.message.reply_html("manca path file!")
        return

    file_path = Path(file_path)
    if file_path.suffix in (".jpg", ".jpeg", ".png", ".webp"):
        await update.effective_message.reply_photo(file_path)
    elif file_path.suffix in (".mp4",):
        await update.effective_message.reply_video(file_path)


@decorators.catch_exception()
@decorators.pass_session()
async def on_comment_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/comment {utilities.log(update)}")

    event: Event = await event_from_link(update, context, session)
    if not event:
        # event_from_link() will also answer in case of error
        return

    if not event.discussion_group_chat_id or not event.discussion_group_message_id:
        logger.info(f"no discussion group message saved for {event}")
        await update.message.reply_text(f"Il messaggio nel gruppo a cui rispondere non è stato salvato", do_quote=True)
        return

    try:
        comment_message_id: MessageId = await update.message.reply_to_message.copy(
            chat_id=event.discussion_group_chat_id,
            reply_parameters=ReplyParameters(
                message_id=event.discussion_group_message_id,
                allow_sending_without_reply=False  # if the discussion group post has been removed, do not send + warn the staff
            )
        )
    except (TelegramError, BadRequest) as e:
        logger.error(f"error while copying message: {e.message}")
        if e.message.lower() == "replied message not found":
            discussion_message_link = event.discussion_group_message_link()
            await update.message.reply_html(
                f"Invio fallito: impossibile trovare <a href=\"{discussion_message_link}\">il messaggio nel gruppo</a> a cui rispondere",
                reply_parameters=ReplyParameters(message_id=update.effective_message.reply_to_message.message_id)
            )
            return
        else:
            raise e

    # we create the ChannelComment because we will not receive this update
    channel_comment = ChannelComment(
        event.discussion_group_chat_id,  # id of the chat we copied the message to
        comment_message_id.message_id,  # result of copy()
        event
    )
    channel_comment.user_id = context.bot.id  # the bot sent the comment
    channel_comment.message_thread_id = event.discussion_group_message_id
    channel_comment.reply_to_message_id = event.discussion_group_message_id  # we replied to the discussion group's message_id

    channel_comment.message_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    channel_comment.message_date = update.message.date  # date of the command we just received

    channel_comment.save_media_metadata(update.message.reply_to_message)
    channel_comment.media_group_id = None  # we override this: /comment does not support albums, so this should be None

    session.add(channel_comment)
    session.commit()

    message_link = utilities.tme_link(event.discussion_group_chat_id, comment_message_id.message_id)
    event_title_link = event.title_link_html()
    await update.message.reply_html(
        f"<a href=\"{message_link}\">Messaggio inviato</a> come commento a \"{event_title_link}\"",
        reply_parameters=ReplyParameters(message_id=update.effective_message.reply_to_message.message_id)
    )

    if config.settings.backup_events:
        # noinspection PyTypeChecker
        file_path: Path = await backup_event_media(update.message.reply_to_message)
        if file_path:
            event.add_media_file_path(file_path)


HANDLERS = (
    (CommandHandler(["events", "feste", "e"], on_events_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["invalidevents", "ie"], on_invalid_events_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["getfilters", "gf"], on_getfilters_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["reparse", "rp"], on_reparse_command, filters=filters.REPLY & filters.ChatType.PRIVATE), Group.NORMAL),
    (CommandHandler(["comment", "replyto", "rt"], on_comment_command, filters=ChatFilter.STAFF & filters.REPLY), Group.NORMAL),
    (CommandHandler(["getpath"], on_getpath_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    # events chat message link actions
    (MessageHandler(filters.ChatType.PRIVATE & Filter.EVENTS_CHAT_MESSAGE_LINK, on_event_chat_message_link), Group.NORMAL),
    (CommandHandler(["postactions"], on_postactions_command, filters=filters.ChatType.PRIVATE), Group.NORMAL),
    (CallbackQueryHandler(on_event_link_action_button, rf"^msglink:(?P<action>\w+):(?P<chat_id>-\d+):(?P<message_id>\d+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_delete_option_button, rf"^delopt:(?P<action>\w+):(?P<chat_id>-\d+):(?P<message_id>\d+)$"), Group.NORMAL),
    # superadmins
    (CommandHandler(["dropeventscache", "dec"], on_drop_events_cache_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
    (CommandHandler(["parseevents", "pe"], on_parse_events_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
