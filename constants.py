from emojis import Emoji
from config import config


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


class BotSettingKey:
    SENT_TO_STAFF = "sent_to_staff_message"
    BROADCAST_EDITS = "broadcast_edits"
    ALLOW_USER_REVOKE = "allow_user_revoke"
    FALLBACK_LANGAUGE = "fallback_language"
    CHAT_INVITE_LINK = "chat_invite_link"
    APPROVAL_MODE = "approval_mode"


class LocalizedTextKey:
    WELCOME = "welcome"
    SENT_TO_STAFF = "sent_to_staff"
    USERNAME_REQUIRED = "username_required"
    WELCOME_MEMBER = "welcome_member"
    WELCOME_NOT_MEMBER = "welcome_not_member"
    SEND_OTHER_MEMBERS = "send_other_members"
    SEND_SOCIAL = "send_social"
    DESCRIBE_SELF = "describe_self"
    APPLICATION_CANCELED = "application_canceled"


LOCALIZED_TEXTS_DESCRIPTORS = {
    LocalizedTextKey.WELCOME: dict(
        label="welcome message",
        explanation="This is the message that will be sent to users when they start the bot",
        emoji=Emoji.HELLO,
        show_if_true_bot_setting_key=None
    ),
    LocalizedTextKey.SENT_TO_STAFF: dict(
        label="\"sent to staff\" message",
        explanation="This is the reply message that will be sent to user when they send a message to the staff",
        emoji=Emoji.PEOPLE,
        show_if_true_bot_setting_key=None
    ),
    LocalizedTextKey.USERNAME_REQUIRED: dict(
        label="username necessario",
        explanation="Il messaggio che verrà inviato agli utenti se non hanno impostato uno username",
        emoji=Emoji.SIGN,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.WELCOME_MEMBER: dict(
        label="benvenuto (membri)",
        explanation="Il messaggio che verrà inviato agli utenti quando avviano il bot, se non fanno parte del gruppo",
        emoji=Emoji.HANDSHAKE,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.WELCOME_NOT_MEMBER: dict(
        label="benvenuto (non membri)",
        explanation="Il messaggio che verrà inviato agli utenti quando avviano il bot, se fanno già parte del gruppo",
        emoji=Emoji.PEACE,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.SEND_OTHER_MEMBERS: dict(
        label="richiesta altri membri",
        explanation="Il messaggio con cui il bot chiederà di inviare i nomi/username degli utenti già nel gruppo",
        emoji=Emoji.BELL,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.SEND_SOCIAL: dict(
        label="richiesta social",
        explanation="Il messaggio con cui il bot chiederà di inviare i link ai social",
        emoji=Emoji.CAMERA,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.DESCRIBE_SELF: dict(
        label="presentazione",
        explanation="Il messaggio con cui il bot chiederà all'utente di presentarsi",
        emoji=Emoji.ALIEN,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.APPLICATION_CANCELED: dict(
        label="richiesta annullata",
        explanation="Il messaggio che verrà inviato all'utente se annulla la procedura di richiesta",
        emoji=Emoji.CANCEL,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
}


class Action:
    READ = "read"
    EDIT = "edit"
    DELETE = "delete"


ACTION_DESCRIPTORS = {
    Action.READ: dict(label="read", emoji="👀"),
    Action.EDIT: dict(label="edit", emoji="✏️"),
    Action.DELETE: dict(label="delete", emoji="❌"),
}


LOCALIZED_TEXTS_TRIGGERS = {
    "welcome": LocalizedTextKey.WELCOME,
    "w": LocalizedTextKey.WELCOME,
    "senttostaff": LocalizedTextKey.SENT_TO_STAFF,
    "sts": LocalizedTextKey.SENT_TO_STAFF,
}


BOT_SETTINGS_DEFAULTS = {
    BotSettingKey.SENT_TO_STAFF: dict(
        default=True,
        label="\"sent to staff\" message",
        emoji=Emoji.ENVELOPE,
        description="when an user sends a message, tell them it has been sent to the staff",
        show_if_true_key=None
    ),
    BotSettingKey.BROADCAST_EDITS: dict(
        default=True,
        label="broadcast edits",
        emoji=Emoji.PENCIL,
        description="edit staff messages sent to users when the original message in the staff chat is edited",
        show_if_true_key=None
    ),
    BotSettingKey.ALLOW_USER_REVOKE: dict(
        default=True,
        label="user messages revoke",
        emoji=Emoji.TRASH,
        description="allow users to revoke the messages forwarded in the staff chat",
        show_if_true_key=None
    ),
    BotSettingKey.CHAT_INVITE_LINK: dict(
        default=config.telegram.chat_invite_link,
        label="chat invite link",
        emoji=Emoji.LINK,
        description="the chat's invite link",
        show_if_true_key=None
    ),
    BotSettingKey.FALLBACK_LANGAUGE: dict(
        default=Language.EN,
        label="fallback language",
        emoji=Emoji.EARTH,
        description="the language that should be used if the user language's version of a text is not available",
        show_if_true_key=None
    ),
    BotSettingKey.APPROVAL_MODE: dict(
        default=False,
        label="approval mode",
        emoji=Emoji.LENS,
        description="approve/refuse users who are not in the users' group chat",
        show_if_true_key=None
    )
}


class TempDataKey:
    FALLBACK_LANGUAGE = "default_language"
    LOCALIZED_TEXTS = "tmp_localized_text_data"
    BOT_SETTINGS = "tmp_bot_setting_data"
    APPLICATION_DATA = "application_data"
    LOCALIZED_TEXTS_LAST_MESSAGE_ID = "localized_text_last_message_id"  # not temp, it is not supposed to be cleaned up
    BOT_SETTINGS_LAST_MESSAGE_ID = "bot_settings_last_message_id"
    DB_INSTANCES = "_database_instances"


COMMAND_PREFIXES = ["/", "!", "."]

CACHE_TIME = 10

CONVERSATION_TIMEOUT = 30 * 60


class Timeout:
    ONE_HOUR = 60 * 60
    MINUTES_30 = 60 * 30
    MINUTES_20 = 60 * 20
    MINUTE_1 = 60
    SECONDS_30 = 30
    SECONDS_10 = 10


ADMIN_HELP = """••• <b><u>Admin commands (private)</u></b>:
•• Only the staff chat's administrators are allowed to use these commands
• /texts: see or edit all messages that should depend on the user's language (that is: the welcome message, \
the \"sent to staff\" message)
• /settings: see the settings' configuration menu
• /oldsettings: see the old setting interface (textual configuration)
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
    WAITING_NEW_SETTING_VALUE = 20


class Group:
    DEBUG = 1
    PREPROCESS = 3
    NORMAL = 5
