import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.ext import filters
from telegram.ext import MessageHandler, CallbackQueryHandler, PrefixHandler, ConversationHandler

from database.models import User, LocalizedText
from database.queries import texts, settings
import decorators
import utilities
from constants import COMMAND_PREFIXES, State, TempDataKey, CONVERSATION_TIMEOUT, Action, \
    LOCALIZED_TEXTS_DESCRIPTORS, LANGUAGES, ACTION_DESCRIPTORS, Group

logger = logging.getLogger(__name__)


def get_localized_texts_list_reply_markup(session: Session) -> InlineKeyboardMarkup:
    keyboard = []
    for ltext_key, ltext_descriptions in LOCALIZED_TEXTS_DESCRIPTORS.items():
        show = True
        setting_key = ltext_descriptions["show_if_true_bot_setting_key"]
        if setting_key:
            show = settings.get_or_create(session, setting_key).value_bool

        if not show:
            continue

        emoji = ltext_descriptions['emoji']
        label = ltext_descriptions['label']
        button = InlineKeyboardButton(f"{emoji} {label}", callback_data=f"lt:actions:{ltext_key}")
        keyboard.append([button])

    return InlineKeyboardMarkup(keyboard)


def get_localized_text_actions_reply_markup(ltext_key, back_button=True) -> InlineKeyboardMarkup:
    keyboard = [[
        InlineKeyboardButton(f"👀 read", callback_data=f"lt:{ltext_key}:{Action.READ}"),
        InlineKeyboardButton(f"✏️ edit", callback_data=f"lt:{ltext_key}:{Action.EDIT}"),
        InlineKeyboardButton(f"❌ delete", callback_data=f"lt:{ltext_key}:{Action.DELETE}"),
    ]]

    if back_button:
        back_button = InlineKeyboardButton(f"🔙 back", callback_data=f"lt:list")
        keyboard.append([back_button])

    return InlineKeyboardMarkup(keyboard)


def get_localized_text_resume_text(session: Session, setting_key: str):
    result = texts.get_texts(session, setting_key)
    ltexts_statuses = {}

    ltext: LocalizedText
    for ltext in result:
        ltexts_statuses[ltext.language] = "set" if ltext.value else "<b>not set</b>"

    for lang_code, lang_data in LANGUAGES.items():
        if lang_code in ltexts_statuses:
            continue

        ltexts_statuses[lang_code] = "<b>not set</b>"

    text = ""
    for lang_code, current_status in ltexts_statuses.items():
        text += f"\n{LANGUAGES[lang_code]['emoji']} -> {current_status}"

    return text.strip()


def get_ltext_action_languages_reply_markup(action: str, ltext_key) -> InlineKeyboardMarkup:
    keyboard = [[]]

    for language_code, language_data in LANGUAGES.items():
        button = InlineKeyboardButton(language_data["emoji"], callback_data=f"lt:langselected:{action}:{ltext_key}:{language_code}")
        keyboard[0].append(button)

    back_button = InlineKeyboardButton(f"🔙 back", callback_data=f"lt:actions:{ltext_key}")
    keyboard.append([back_button])

    return InlineKeyboardMarkup(keyboard)


def get_localized_texts_main_text(ltexts_resume, ltext_key, ltext_description):
    explanation = LOCALIZED_TEXTS_DESCRIPTORS[ltext_key]['explanation']
    emoji = LOCALIZED_TEXTS_DESCRIPTORS[ltext_key]['emoji']
    return f"{emoji} <b>{ltext_description}</b> settings\n" \
           f"<i>{explanation}</i>\n\n" \
           f"{ltexts_resume}\n\n" \
           f"Use the buttons below to read/edit/delete a language's {ltext_description}:"


@decorators.catch_exception()
@decorators.pass_session()
async def on_ltexts_list_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized texts list button {utilities.log(update)}")

    reply_markup = get_localized_texts_list_reply_markup(session)
    text = f"Select the text to read/edit/delete it:"
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_localized_text_action_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized text action button {utilities.log(update)}")
    ltext_key = context.matches[0].group("key")
    action = context.matches[0].group("action")
    ltext_description = LOCALIZED_TEXTS_DESCRIPTORS[ltext_key]["label"]

    reply_markup = get_ltext_action_languages_reply_markup(action, ltext_key)
    text = f"{ACTION_DESCRIPTORS[action]['emoji']} {ltext_description}: select the language 👇"
    await utilities.edit_text_safe(update, text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_localized_text_actions_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized text actions button {utilities.log(update)}")
    ltext_key = context.matches[0].group("key")
    ltext_description = LOCALIZED_TEXTS_DESCRIPTORS[ltext_key]["label"]

    reply_markup = get_localized_text_actions_reply_markup(ltext_key)
    settings_resume = get_localized_text_resume_text(session, ltext_key)
    text = get_localized_texts_main_text(settings_resume, ltext_key, ltext_description)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_localized_text_read_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized text read {utilities.log(update)}")
    ltext_key = context.matches[0].group("key")
    language = context.matches[0].group("lang")
    action = context.matches[0].group("action")
    language_emoji = LANGUAGES[language]["emoji"]
    ltext_description = LOCALIZED_TEXTS_DESCRIPTORS[ltext_key]["label"]

    ltext = texts.get_localized_text(
        session,
        key=ltext_key,
        language=language,
        create_if_missing=False
    )
    if not ltext:
        await update.callback_query.answer(f"There's no {ltext_description} set for {language_emoji}")
        return

    reply_markup = get_ltext_action_languages_reply_markup(action, ltext_key)
    text = f"Current {ltext_description} for {language_emoji}:\n\n{ltext.value}"
    await utilities.edit_text_safe(update, text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_localized_text_delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized text delete {utilities.log(update)}")
    ltext_key = context.matches[0].group("key")
    language = context.matches[0].group("lang")
    action = context.matches[0].group("action")
    language_emoji = LANGUAGES[language]["emoji"]
    ltext_description = LOCALIZED_TEXTS_DESCRIPTORS[ltext_key]["label"]

    ltext = texts.get_localized_text(
        session,
        key=ltext_key,
        language=language,
        create_if_missing=False
    )
    if ltext:
        session.delete(ltext)

    reply_markup = get_ltext_action_languages_reply_markup(action, ltext_key)
    text = f"{ACTION_DESCRIPTORS[action]['emoji']} {ltext_description}: select the language 👇"
    await update.callback_query.answer(f"{ltext_description} deleted for {language_emoji}")
    await utilities.edit_text_safe(update, text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session(pass_user=True)
@decorators.staff_member()
async def on_ltexts_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    logger.info(f"/texts {utilities.log(update)}")

    reply_markup = get_localized_texts_list_reply_markup(session)
    text = f"Select the text to read/edit/delete it:"
    sent_message = await update.message.reply_text(text, reply_markup=reply_markup)

    # save this emssage's message_id and remove the last message's keyboard
    remove_keyboard_message_id = context.user_data.get(TempDataKey.LOCALIZED_TEXTS_LAST_MESSAGE_ID, None)
    if remove_keyboard_message_id:
        await utilities.remove_reply_markup_safe(context.bot, update.effective_user.id, remove_keyboard_message_id)
    context.user_data[TempDataKey.LOCALIZED_TEXTS_LAST_MESSAGE_ID] = sent_message.message_id


@decorators.catch_exception()
@decorators.pass_session()
async def on_localized_text_edit_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"localized text edit {utilities.log(update)}")
    ltext_key = context.matches[0].group("key")
    language = context.matches[0].group("lang")
    language_emoji = LANGUAGES[language]["emoji"]
    ltext_description = LOCALIZED_TEXTS_DESCRIPTORS[ltext_key]["label"]

    context.user_data[TempDataKey.LOCALIZED_TEXTS] = dict(key=ltext_key, lang=language)
    await update.effective_message.edit_text(f"Please send me the new <b>{ltext_description}</b> text for {language_emoji} "
                                             f"(or use /cancel to cancel):")

    return State.WAITING_NEW_LOCALIZED_TEXT


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_localized_text_receive(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"received new localized text {utilities.log(update)})")

    ltext_data = context.user_data.pop(TempDataKey.LOCALIZED_TEXTS)
    ltext_key = ltext_data["key"]
    ltext_language = ltext_data["lang"]

    ltext_description = LOCALIZED_TEXTS_DESCRIPTORS[ltext_key]["label"]
    ltext_show_if_true_bot_setting_key = LOCALIZED_TEXTS_DESCRIPTORS[ltext_key]["show_if_true_bot_setting_key"]
    lang_emoji = LANGUAGES[ltext_language]['emoji']

    ltext = texts.get_localized_text(
        session,
        key=ltext_key,
        language=ltext_language,
        create_if_missing=True,
        show_if_true_bot_setting_key=ltext_show_if_true_bot_setting_key
    )
    ltext.value = update.effective_message.text_html
    ltext.save_updated_by(update.effective_user)

    await update.effective_message.reply_text(f"{ltext_description} set for {lang_emoji}:\n\n{ltext.value}")

    reply_markup = get_ltext_action_languages_reply_markup(Action.EDIT, ltext_key)
    text = f"{ACTION_DESCRIPTORS[Action.EDIT]['emoji']} {ltext_description}: select the language 👇"
    await update.effective_message.reply_text(text, reply_markup=reply_markup)

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_localized_text_receive_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"(unexpected) received new localized text message {utilities.log(update)}")

    await update.message.reply_text("Please send me the new text for the selected language")

    return State.WAITING_NEW_LOCALIZED_TEXT


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_localized_text_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"waiting for new localized text: timed out")

    ltext_data = context.user_data.pop(TempDataKey.LOCALIZED_TEXTS, None)
    ltext_description = LOCALIZED_TEXTS_DESCRIPTORS[ltext_data['key']]["label"]

    await update.effective_message.reply_text(f"Okay, it looks like you forgot... "
                                              f"I'm exiting the {ltext_description} configuration")

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_localized_text_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"waiting new localized text: /cancel command {utilities.log(update)}")

    context.user_data.pop(TempDataKey.LOCALIZED_TEXTS, None)

    await update.effective_message.reply_text("Okay, operation canceled :)")

    return ConversationHandler.END


edit_ltext_conversation_handler = ConversationHandler(
    name="ltext_conversation",
    entry_points=[CallbackQueryHandler(on_localized_text_edit_button, rf"lt:langselected:(?P<action>{Action.EDIT}):(?P<key>\w+):(?P<lang>\w+)$")],
    states={
        State.WAITING_NEW_LOCALIZED_TEXT: [
            PrefixHandler(COMMAND_PREFIXES, "cancel", on_localized_text_cancel_command),
            MessageHandler(filters.TEXT, on_localized_text_receive),
            MessageHandler(~filters.TEXT, on_localized_text_receive_unexpected)
        ],
        ConversationHandler.TIMEOUT: [
            # on timeout, the *last update* is broadcasted to all users. it might be a callback query or a text
            MessageHandler(filters.ALL, on_localized_text_timeout),
            CallbackQueryHandler(on_localized_text_timeout, ".*"),
        ]
    },
    fallbacks=[
        PrefixHandler(COMMAND_PREFIXES, "cancel", on_localized_text_cancel_command)
    ],
    conversation_timeout=CONVERSATION_TIMEOUT
)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ['texts', 't'], on_ltexts_list_command, filters.ChatType.PRIVATE), Group.NORMAL),
    (CallbackQueryHandler(on_ltexts_list_button, rf"lt:list$"), Group.NORMAL),
    (CallbackQueryHandler(on_localized_text_actions_button, rf"lt:actions:(?P<key>\w+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_localized_text_action_button, rf"lt:(?P<key>\w+):(?P<action>\w+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_localized_text_read_button, rf"lt:langselected:(?P<action>{Action.READ}):(?P<key>\w+):(?P<lang>\w+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_localized_text_delete_button, rf"lt:langselected:(?P<action>{Action.DELETE}):(?P<key>\w+):(?P<lang>\w+)$"), Group.NORMAL),
    (edit_ltext_conversation_handler, Group.NORMAL)
)
