LANGUAGES = {
    "it": {
        "emoji": "🇮🇹",
        "desc": "italiano",
        "desc_en": "italian"
    },
    "fr": {
        "emoji": "🇫🇷",
        "desc": "français",
        "desc_en": "french"
    },
    "es": {
        "emoji": "🇪🇸",
        "desc": "español",
        "desc_en": "spanish"
    },
    "en": {
        "emoji": "🇬🇧",
        "desc": "english",
        "desc_en": "english"
    },
}


class SettingKey:
    WELCOME = "welcome"
    SENT_TO_STAFF = "sent_to_staff"


class BotSettingKey:
    SENT_TO_STAFF = "sent_to_staff_message"
    BROADCAST_EDITS = "broadcast_edits"
    ALLOW_USER_REVOKE = "allow_user_revoke"


BOT_SETTINGS_DEFAULTS = {
    BotSettingKey.SENT_TO_STAFF: dict(default=True, description="when an user sends a message, tell them it has been sent to the staff"),
    BotSettingKey.BROADCAST_EDITS: dict(default=True, description="edit staff messages sent to users when the original message in the staff chat is edited"),
    BotSettingKey.ALLOW_USER_REVOKE: dict(default=True, description="allow users to revoke the messages forwarded in the staff chat")
}


class TempDataKey:
    WELCOME_LANGUAGE = "_welcome_language"


class Language:
    EN = "en"
    IT = "it"
    FR = "fr"
    ES = "es"


COMMAND_PREFIXES = ["/", "!", "."]

CACHE_TIME = 10

ADMIN_HELP = """••• <b><u>Admin commands (private)</u></b>:
•• Only the staff chat's administrators are allowed to use these commands
• /welcome: see or edit a langauge's welcome text
• /placeholders: list available placeholders (they can be used in welcome texts)
• /settings: list all available settings
• /set <code>[setting] [new value]</code>: change a setting

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
    WAITING_WELCOME = 10
    WAITING_SENT_TO_STAFF_MESSAGE = 20
