import logging
import tempfile

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes, filters, PrefixHandler

import decorators
import utilities
from constants import COMMAND_PREFIXES, Group, TempDataKey

logger = logging.getLogger(__name__)


@decorators.catch_exception()
@decorators.pass_session()
@decorators.staff_member()
async def on_diff_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    logger.info(f"/diff {utilities.log(update)}")

    replied_to_message = update.message.reply_to_message
    if not replied_to_message.text and not replied_to_message.caption:
        await update.message.reply_text(f"Please reply to a message with a text or a caption")
        return

    if not context.args:
        await update.message.reply_text(f"Please provide a number (1 for the first text, 2 for the second text)")
        return

    diff_arg = context.args[0]
    if diff_arg not in ("1", "2"):
        await update.message.reply_text(f"\"{diff_arg}\" is not a valid argument, use 1 or 2")
        return

    text = replied_to_message.caption if replied_to_message.caption else replied_to_message.text
    diff_arg = int(diff_arg)
    if diff_arg == 1:
        context.user_data[TempDataKey.FIRST_DIFF_TEXT] = text
        await replied_to_message.reply_text(f"Saved, use <code>/diff 2</code> or <code>/altdiff 2</code> in reply to the other text you want to use")
        return

    if diff_arg == 2 and TempDataKey.FIRST_DIFF_TEXT not in context.user_data:
        await update.message.reply_text(f"Use <code>/diff 1</code> first")
        return

    string1 = context.user_data.pop(TempDataKey.FIRST_DIFF_TEXT)
    string2 = text

    command = utilities.get_command(update.message.text)
    result = ""
    if command == "diff":
        result = utilities.diff(string1, string2)
    elif command == "altdiff":
        result = utilities.diff_alt(string1, string2, ignore_context_lines=True)

    try:
        file_to_send = tempfile.SpooledTemporaryFile(mode="w+b")
        file_to_send.write(result.encode())
        file_to_send.seek(0)

        await update.message.reply_document(file_to_send.read(), filename="diff.txt")

        file_to_send.close()
    except Exception as e:
        await update.message.reply_text(f"error while creating and sending the diff file: {e}")


HANDLERS = (
    (PrefixHandler(COMMAND_PREFIXES, ['diff', 'altdiff'], on_diff_command, filters.ChatType.PRIVATE), Group.NORMAL),
)
