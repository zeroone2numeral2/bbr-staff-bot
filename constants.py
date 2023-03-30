class Language:
    EN = "en"
    IT = "it"
    FR = "fr"
    ES = "es"


LANGUAGES = {
    Language.IT: {
        "emoji": "🇮🇹",
        "desc": "italiano",
        "desc_en": "italian"
    },
    Language.FR: {
        "emoji": "🇫🇷",
        "desc": "français",
        "desc_en": "french"
    },
    Language.ES: {
        "emoji": "🇪🇸",
        "desc": "español",
        "desc_en": "spanish"
    },
    Language.EN: {
        "emoji": "🇬🇧",
        "desc": "english",
        "desc_en": "english"
    },
}


class LocalizedTextKey:
    WELCOME = "welcome"
    SENT_TO_STAFF = "sent_to_staff"


LOCALIZED_TEXTS_DESCRIPTIONS = {
    LocalizedTextKey.WELCOME: dict(
        label="welcome message",
        explanation="This is the message that will be sent to users when they start the bot",
        emoji="👋"
    ),
    LocalizedTextKey.SENT_TO_STAFF: dict(
        label="\"sent to staff\" message",
        explanation="This is the reply message that will be sent to user when they send a message to the staff",
        emoji="👥"
    ),
}


class Action:
    READ = "read"
    EDIT = "edit"
    DELETE = "delete"


ACTION_ICONS = {
    Action.READ: "👀",
    Action.EDIT: "✏️",
    Action.DELETE: "❌",
}

LOCALIZED_TEXTS_TRIGGERS = {
    "welcome": LocalizedTextKey.WELCOME,
    "w": LocalizedTextKey.WELCOME,
    "senttostaff": LocalizedTextKey.SENT_TO_STAFF,
    "sts": LocalizedTextKey.SENT_TO_STAFF,
}


class BotSettingKey:
    SENT_TO_STAFF = "sent_to_staff_message"
    BROADCAST_EDITS = "broadcast_edits"
    ALLOW_USER_REVOKE = "allow_user_revoke"
    FALLBACK_LANGAUGE = "fallback_language"


BOT_SETTINGS_DEFAULTS = {
    BotSettingKey.SENT_TO_STAFF: dict(
        default=True,
        label="\"sent to staff\" message",
        emoji="✉️",
        description="when an user sends a message, tell them it has been sent to the staff"
    ),
    BotSettingKey.BROADCAST_EDITS: dict(
        default=True,
        label="broadcast edits",
        emoji="✏️",
        description="edit staff messages sent to users when the original message in the staff chat is edited"
    ),
    BotSettingKey.ALLOW_USER_REVOKE: dict(
        default=True,
        label="user messages revoke",
        emoji="🚮",
        description="allow users to revoke the messages forwarded in the staff chat"
    ),
    BotSettingKey.FALLBACK_LANGAUGE: dict(
        default=Language.EN,
        label="fallback language",
        emoji="🌍",
        description="the language that should be used if the user language's version of a text is not available"
    )
}


class TempDataKey:
    FALLBACK_LANGUAGE = "default_language"
    LOCALIZED_TEXTS = "tmp_localized_text_data"
    LOCALIZED_TEXTS_LAST_MESSAGE_ID = "localized_text_last_message_id"  # not temp, it is not supposed to be cleaned up


COMMAND_PREFIXES = ["/", "!", "."]

CACHE_TIME = 10

ADMIN_HELP = """••• <b><u>Admin commands (private)</u></b>:
•• Only the staff chat's administrators are allowed to use these commands
• /texts: see or edit all messages that should depend on the user's language (that is: the welcome message, \
the \"sent to staff\" message)
• /settings: list all available settings
• /set <code>[setting] [new value]</code>: change a setting
• /placeholders: list available placeholders (they can be used in welcome texts)

••• <b><u>Staff chat commands</u></b>:
•• Anyone in the staff chat is allowed to use these commands or perform these actions
• <code>/reloadadmins</code>: update the staff chat's admins list
• <code>/revoke</code> or <code>/del</code> (in reply to an admin message): delete an admin's reply from the user's private chat
• <code>++[reply]</code>: you can reply to an admin's message that was previously sent to the user by answering it with \
"<code>++</code>". The text after "<code>++</code>" will be sent to the user <b>in reply</b> to the admin message they \
previously received

•• The following commands work in reply to an user's forwarded message in the staff chat:
• <code>/ban [reason]</code>: ban an user from using the bot. The bot will tell the user that they are banned \
when they send new messages. The reason is optional
• <code>/shadowban [reason]</code>: like <code>/ban</code>, but the user won't know they were banned
• <code>/unban</code>: unban the user
• <code>/info</code>: show everything we know about that user

••• <b><u>Other</u></b>:
• all commands work with <code>/</code>, <code>!</code> and <code>.</code> as triggers
"""


class State:
    WAITING_NEW_LOCALIZED_TEXT = 10
    WAITING_SENT_TO_STAFF_MESSAGE = 20
