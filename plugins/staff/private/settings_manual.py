import logging
import re

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, PrefixHandler, filters

import decorators
import utilities
from constants import BOT_SETTINGS_DEFAULTS, COMMAND_PREFIXES, Group
from database.models import BotSetting, ValueType
from database.queries import settings

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_oldsettings_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/oldsettings {utilities.log(update)}")

    all_settings = settings.get_settings(session)
    text = ""
    setting: BotSetting
    for setting in all_settings:
        text += f"•• [<code>{setting.value_type}</code>] <code>{setting.key}</code> -{utilities.escape_html('>')} {setting.value_pretty()}\n" \
                f"• <i>{BOT_SETTINGS_DEFAULTS[setting.key]['description']}</i>\n\n"

    text += "\nTo change a setting, use <code>/set [setting] [new value]</code>\n" \
            "For settings of type <code>bool</code>, you can also use the <code>/enable</code> or " \
            "<code>/disable</code> commands: <code>/enable [setting]</code>\n\n" \
            "Examples:\n" \
            "• <code>/set broadcast_edits false</code>\n" \
            "• <code>/enable sent_to_staff_message</code>\n\n" \
            "Settings of type <code>bool</code> can be changed using the values " \
            "'true' and 'false', 'none' or 'null' can be used to set a setting to <code>NULL</code>\n" \
            "<code>int</code>, <code>float</code>, <code>str</code>, <code>datetime</code> and <code>date</code> " \
            "are auto-detected"

    await update.message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/set {utilities.log(update)}")

    try:
        key = context.args[0].lower()
        value = context.args[1]
    except IndexError:
        await update.message.reply_text(f"Usage: <code>/set [setting] [value]</code>\nUse /settings for a list of settings")
        return

    if key not in BOT_SETTINGS_DEFAULTS:
        await update.message.reply_text(f"<code>{key}</code> is not a recognized setting")
        return

    value = utilities.convert_string_to_value(value)

    setting = settings.get_or_create(session, key, value=value)
    setting.update_value(value)
    session.add(setting)

    text = f"New value for <code>{key}</code>: {setting.value_pretty()}"
    await update.message.reply_text(text)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_admin()
async def on_enable_disable_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/enable or /disable {utilities.log(update)}")

    command = re.search(r"^.(enable|disable).*", update.message.text, re.I).group(1).lower()

    try:
        key = context.args[0].lower()
    except IndexError:
        await update.message.reply_text(f"Usage: <code>/{command} [setting]</code>\nUse /settings for a list of settings. "
                                        f"Only <code>bool</code> settings can be enabled/disabled")
        return

    if key not in BOT_SETTINGS_DEFAULTS:
        await update.message.reply_text(f"<code>{key}</code> is not a recognized setting")
        return

    value = True if command == "enable" else False

    setting = settings.get_or_create(session, key, value=value)
    if setting.value_type != ValueType.BOOL:
        await update.message.reply_text(f"<code>{key}</code> is not a boolean setting that can be enabled/disabled")
        return

    logger.info(f"new value for {key}: {value}")

    setting.update_value(value)
    session.add(setting)

    text = f"<code>{key}</code> {command}d"
    await update.message.reply_text(text)


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ['oldsettings', 'os'], on_oldsettings_command, filters.ChatType.PRIVATE), Group.NORMAL),
    (PrefixHandler(COMMAND_PREFIXES, ['set'], on_set_command, filters.ChatType.PRIVATE), Group.NORMAL),
    (PrefixHandler(COMMAND_PREFIXES, ['enable', 'disable'], on_enable_disable_command, filters.ChatType.PRIVATE), Group.NORMAL),
)
