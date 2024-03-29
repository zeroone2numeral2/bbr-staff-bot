import logging
from typing import Optional

from sqlalchemy.orm import Session
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram import Update
from telegram.ext import ContextTypes
from telegram.ext import MessageHandler, CallbackQueryHandler, PrefixHandler, ConversationHandler
from telegram.ext import filters

import decorators
import utilities
from constants import COMMAND_PREFIXES, State, TempDataKey, BOT_SETTINGS_DEFAULTS, CONVERSATION_TIMEOUT, Group, \
    BOT_SETTINGS_CATEGORIES_METADATA
from database.models import BotSetting, ValueType
from database.models import User
from database.queries import settings
from emojis import Emoji

logger = logging.getLogger(__name__)

FILTER_MEDIA = filters.PHOTO \
               | filters.VIDEO \
               | filters.Sticker.ALL \
               | filters.Document.ALL \
               | filters.VOICE \
               | filters.VIDEO_NOTE \
               | filters.AUDIO \
               | filters.ANIMATION


def get_setting_actions_reply_markup(setting: BotSetting, back_button=True) -> InlineKeyboardMarkup:
    keyboard = []
    if setting.value_type == ValueType.BOOL:
        if setting.value():
            button = InlineKeyboardButton(f"☑️ disable", callback_data=f"bs:setbool:false:{setting.key}")
        else:
            button = InlineKeyboardButton(f"✅ enable", callback_data=f"bs:setbool:true:{setting.key}")
        keyboard.append([button])
    elif setting.value_type == ValueType.MEDIA:
        row = [
            InlineKeyboardButton(f"✏️ edit", callback_data=f"bs:editmedia:{setting.key}"),
            InlineKeyboardButton(f"⚫️ nullify", callback_data=f"bs:null:{setting.key}")
        ]
        if setting.value_media_file_id:
            row.append(InlineKeyboardButton(f"📎 test", callback_data=f"bs:testmedia:{setting.key}"))

        keyboard.append(row)
    else:
        keyboard.append([
            InlineKeyboardButton(f"✏️ edit", callback_data=f"bs:edit:{setting.key}"),
            InlineKeyboardButton(f"⚫️ nullify", callback_data=f"bs:null:{setting.key}")
        ])

    if back_button:
        back_button = InlineKeyboardButton(f"🔙 back", callback_data=f"bs:category:{setting.category}")
        keyboard.append([back_button])

    return InlineKeyboardMarkup(keyboard)


def get_bot_settings_list_reply_markup(
        session: Session,
        include_category: Optional[str] = None,
        exclude_category: Optional[str] = None,
        add_back_button=True
) -> InlineKeyboardMarkup:
    keyboard = []

    settings_dict = settings.get_settings_as_dict(
        session,
        include_categories=include_category,
        exclude_categories=exclude_category
    )

    for setting_key, setting in settings_dict.items():
        if setting_key not in BOT_SETTINGS_DEFAULTS:
            logger.debug(f"ignoring setting <{setting_key}>")
            continue

        # print(setting.key, setting.show_if_true)
        if setting.show():
            emoji = BOT_SETTINGS_DEFAULTS[setting_key]["emoji"]
            label = BOT_SETTINGS_DEFAULTS[setting_key]["label"]
            button = InlineKeyboardButton(f"{emoji} {label}", callback_data=f"bs:actions:{setting_key}")
            keyboard.append([button])

    if add_back_button:
        keyboard.append([InlineKeyboardButton(f"{Emoji.BACK} back", callback_data=f"bs:showcategories")])

    return InlineKeyboardMarkup(keyboard)


def get_bot_settings_categories_reply_markup() -> InlineKeyboardMarkup:
    keyboard = []

    for category_key, category_data in BOT_SETTINGS_CATEGORIES_METADATA.items():
        emoji = category_data["emoji"]
        label = category_data["label"]
        button = InlineKeyboardButton(f"{emoji} {label}", callback_data=f"bs:category:{category_key}")
        keyboard.append([button])

    return InlineKeyboardMarkup(keyboard)


def get_setting_text(setting: BotSetting):
    setting_descriptors = BOT_SETTINGS_DEFAULTS[setting.key]
    return f"{setting_descriptors['emoji']} <b>{setting_descriptors['label']}</b>\n" \
           f"<i>{setting_descriptors['description']}</i>\n\n" \
           f"Current value [<code>{setting.value_type}</code>]: {setting.value_pretty()}"


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/settings {utilities.log(update)}")

    reply_markup = get_bot_settings_categories_reply_markup()
    text = f"Select a category:"
    sent_message = await update.message.reply_text(text, reply_markup=reply_markup)

    # save this emssage's message_id and remove the last message's keyboard
    remove_keyboard_message_id = context.user_data.get(TempDataKey.BOT_SETTINGS_LAST_MESSAGE_ID, None)
    if remove_keyboard_message_id:
        await utilities.remove_reply_markup_safe(context.bot, update.effective_user.id, remove_keyboard_message_id)
    context.user_data[TempDataKey.BOT_SETTINGS_LAST_MESSAGE_ID] = sent_message.message_id


@decorators.catch_exception()
@decorators.pass_session()
async def on_settings_show_categories_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"settings categories button {utilities.log(update)}")

    reply_markup = get_bot_settings_categories_reply_markup()
    text = f"Select a category:"
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_bot_setting_show_setting_actions_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"bot setting show actions button {utilities.log(update)}")
    setting_key = context.matches[0].group("key")

    setting: BotSetting = settings.get_or_create(session, setting_key)
    reply_markup = get_setting_actions_reply_markup(setting)
    text = get_setting_text(setting)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_category_select_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"category button {utilities.log(update)}")
    category_key = context.matches[0].group("cat_key")

    reply_markup = get_bot_settings_list_reply_markup(session, include_category=category_key)
    label = BOT_SETTINGS_CATEGORIES_METADATA[category_key]["label"]
    emoji = BOT_SETTINGS_CATEGORIES_METADATA[category_key]["emoji"]
    text = f"{emoji} <b>{label}</b>\nSelect the setting to edit:"

    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_bot_setting_switch_bool_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"bot setting switch bool button {utilities.log(update)}")
    setting_key = context.matches[0].group("key")
    new_value = context.matches[0].group("value")
    new_value = utilities.convert_string_to_value(new_value)

    setting: BotSetting = settings.get_or_create(session, setting_key)
    setting.update_value(new_value)
    reply_markup = get_setting_actions_reply_markup(setting)
    text = get_setting_text(setting)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


@decorators.catch_exception(ignore_message_not_modified_exception=True)
@decorators.pass_session()
async def on_bot_setting_nullify_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"bot setting nullify button {utilities.log(update)}")
    setting_key = context.matches[0].group("key")

    setting: BotSetting = settings.get_or_create(session, setting_key)
    setting.update_null()

    await update.callback_query.answer(f"{Emoji.WARNING} Be careful when you \"nullify\" a setting! "
                                       f"It might break some of the bot's functionalities", show_alert=True)

    reply_markup = get_setting_actions_reply_markup(setting)
    text = get_setting_text(setting)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)


@decorators.catch_exception()
@decorators.pass_session()
async def on_bot_setting_test_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"bot setting test media button {utilities.log(update)}")
    setting_key = context.matches[0].group("key")

    setting: BotSetting = settings.get_or_create(session, setting_key)

    await update.callback_query.answer(f"sending media of type {setting.value_media_type}...")
    await utilities.reply_media(update.effective_message, setting.value_media_type, setting.value_media_file_id, quote=True)


@decorators.catch_exception()
@decorators.pass_session()
async def on_bot_setting_edit_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"non-bool bot setting edit {utilities.log(update)}")
    setting_key = context.matches[0].group("key")
    setting_label = BOT_SETTINGS_DEFAULTS[setting_key]["label"]
    setting_emoji = BOT_SETTINGS_DEFAULTS[setting_key]["emoji"]

    context.user_data[TempDataKey.BOT_SETTINGS] = dict(key=setting_key)
    await update.effective_message.edit_text(f"Please send me the new value for {setting_emoji} <b>{setting_label}</b> "
                                             f"(or use /cancel to cancel):")

    return State.WAITING_NEW_SETTING_VALUE


@decorators.catch_exception()
@decorators.pass_session()
async def on_bot_setting_edit_media_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Optional[Session] = None):
    logger.info(f"media bot setting edit {utilities.log(update)}")
    setting_key = context.matches[0].group("key")
    setting_label = BOT_SETTINGS_DEFAULTS[setting_key]["label"]
    setting_emoji = BOT_SETTINGS_DEFAULTS[setting_key]["emoji"]

    context.user_data[TempDataKey.BOT_SETTINGS] = dict(key=setting_key)
    await update.effective_message.edit_text(f"Please send me the new media for {setting_emoji} <b>{setting_label}</b> "
                                             f"(or use /cancel to cancel):")

    return State.WAITING_NEW_SETTING_VALUE_MEDIA


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_new_setting_value_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"waiting new setting value: /cancel command {utilities.log(update)}")

    context.user_data.pop(TempDataKey.BOT_SETTINGS, None)

    await update.effective_message.reply_text("Okay, operation canceled :)")

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_new_setting_value_receive(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"received new setting value {utilities.log(update)})")

    setting_data = context.user_data.pop(TempDataKey.BOT_SETTINGS)
    setting_key = setting_data["key"]

    setting_label = BOT_SETTINGS_DEFAULTS[setting_key]["label"]
    setting_emoji = BOT_SETTINGS_DEFAULTS[setting_key]["emoji"]

    setting = settings.get_or_create(session, setting_key)
    if not utilities.contains_media_with_file_id(update.message):
        logger.info("new setting is text")
        setting.update_value(utilities.convert_string_to_value(update.effective_message.text_html))
    else:
        logger.info("new setting is a media")
        file_id, file_unique_id, _ = utilities.get_media_ids(update.message)
        setting.update_value_telegram_media(file_id, file_unique_id, utilities.detect_media_type(update.message))

    setting.updated_by = update.effective_user.id

    await update.effective_message.reply_text(f"{setting_emoji} <b>{setting_label}</b> updated:\n\n{setting.value_pretty()}")

    reply_markup = get_setting_actions_reply_markup(setting)
    text = get_setting_text(setting)
    await update.effective_message.reply_text(text, reply_markup=reply_markup)

    return ConversationHandler.END


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_new_setting_value_receive_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"(unexpected) received new setting value {utilities.log(update)}")

    await update.message.reply_text("Please send me the new value for the selected setting")

    return State.WAITING_NEW_SETTING_VALUE


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_new_setting_value_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"waiting for new setting value: timed out")

    setting_data = context.user_data.pop(TempDataKey.BOT_SETTINGS, None)
    setting_label = BOT_SETTINGS_DEFAULTS[setting_data['key']]["label"]
    setting_emoji = BOT_SETTINGS_DEFAULTS[setting_data['key']]["label"]

    await update.effective_message.reply_text(f"Okay, it looks like you forgot {Emoji.SLEEPING}"
                                              f"I'm exiting the {setting_emoji} <b>{setting_label}</b> configuration")

    return ConversationHandler.END


edit_nonbool_setting_conversation_handler = ConversationHandler(
    name="bot_settings_conversation",
    entry_points=[
        CallbackQueryHandler(on_bot_setting_edit_button, rf"bs:edit:(?P<key>\w+)$"),
        CallbackQueryHandler(on_bot_setting_edit_media_button, rf"bs:editmedia:(?P<key>\w+)$"),
    ],
    states={
        State.WAITING_NEW_SETTING_VALUE: [
            PrefixHandler(COMMAND_PREFIXES, "cancel", on_new_setting_value_cancel_command),
            MessageHandler(filters.TEXT, on_new_setting_value_receive),
            MessageHandler(~filters.TEXT, on_new_setting_value_receive_unexpected)
        ],
        State.WAITING_NEW_SETTING_VALUE_MEDIA: [
            PrefixHandler(COMMAND_PREFIXES, "cancel", on_new_setting_value_cancel_command),
            MessageHandler(FILTER_MEDIA, on_new_setting_value_receive),
            MessageHandler(~filters.TEXT, on_new_setting_value_receive_unexpected)
        ],
        ConversationHandler.TIMEOUT: [
            # on timeout, the *last update* is broadcasted to all users. it might be a callback query or a text
            MessageHandler(filters.ALL, on_new_setting_value_timeout),
            CallbackQueryHandler(on_new_setting_value_timeout, ".*"),
        ]
    },
    fallbacks=[
        PrefixHandler(COMMAND_PREFIXES, "cancel", on_new_setting_value_cancel_command)
    ],
    conversation_timeout=CONVERSATION_TIMEOUT
)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ['settings', 's'], on_settings_command, filters.ChatType.PRIVATE), Group.NORMAL),
    (CallbackQueryHandler(on_settings_show_categories_button, rf"bs:showcategories$"), Group.NORMAL),
    (CallbackQueryHandler(on_category_select_button, rf"bs:category:(?P<cat_key>\w+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_bot_setting_show_setting_actions_button, rf"bs:actions:(?P<key>\w+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_bot_setting_switch_bool_button, rf"bs:setbool:(?P<value>\w+):(?P<key>\w+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_bot_setting_nullify_button, rf"bs:null:(?P<key>\w+)$"), Group.NORMAL),
    (CallbackQueryHandler(on_bot_setting_test_button, rf"bs:testmedia:(?P<key>\w+)$"), Group.NORMAL),
    (edit_nonbool_setting_conversation_handler, Group.NORMAL),
)
