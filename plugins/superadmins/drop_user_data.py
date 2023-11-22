import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import decorators
import utilities
from constants import Group
from ext.filters import Filter

logger = logging.getLogger(__name__)


@decorators.catch_exception()
async def on_drop_persistence_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/dropuserdata {utilities.log(update)}")

    user_ids_to_pop = []
    for user_id, user_data_dict in context.application.user_data.items():
        if user_data_dict:
            user_ids_to_pop.append(user_id)

    for user_id in user_ids_to_pop:
        logger.info(f"dropping existign user data for {user_id}...")
        context.application._user_data.pop(user_id)

    await update.message.reply_text(f"dropped user data for {len(user_ids_to_pop)} users")


HANDLERS = (
    (CommandHandler(["dropuserdata", "dud"], on_drop_persistence_command, filters=Filter.SUPERADMIN_AND_PRIVATE), Group.NORMAL),
)
