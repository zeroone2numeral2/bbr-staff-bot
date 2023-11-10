from emojis import Emoji, Flag

MONTHS_IT = [
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre"
]

WEEKDAYS_IT = [
    "lunedì",
    "martedì",
    "mercoledì",
    "giovedì",
    "venerdì",
    "sabato",
    "domenica"
]


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


class HandlersMode:
    FLYTEK = "flytek"
    BBR = "bbr"


class DeeplinkParam:
    RADAR = "radar"
    RADAR_UNLOCK = "radarunlock"
    RADAR_UNLOCK_TRIGGER = "radargo"


class MediaType:
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    STICKER = "sticker"
    ANIMATION = "animation"
    VIDEO_NOTE = "video_note"
    VOICE = "voice"
    AUDIO = "audio"


class BotSettingKey:
    SENT_TO_STAFF = "sent_to_staff_message"
    BROADCAST_EDITS = "broadcast_edits"
    ALLOW_USER_REVOKE = "allow_user_revoke"
    FALLBACK_LANGAUGE = "fallback_language"
    CHAT_INVITE_LINK = "chat_invite_link"
    APPROVAL_MODE = "approval_mode"
    RABBIT_FILE = "rabbit_file"
    RADAR_FILE = "radar_file"
    PARTIES_LIST = "parties_list"
    PARTIES_LIST_WEEKS = "parties_list_weeks"
    PARTIES_LIST_UPDATE_ONLY = "parties_list_update_only"
    PARTIES_LIST_WEEKDAY = "parties_list_weekday"
    PARTIES_LIST_HOUR = "parties_list_hour"
    PARTIES_LIST_PIN = "parties_list_pin"
    PARTIES_LIST_DISCUSSION_LINK = "parties_list_discussion_link"


class BotSettingCategory:
    GENERAL = "general"
    PARTIES_LIST = "parties_list"
    REQUESTS = "requests"
    RADAR = "radar"
    USER_MESSAGES = "user_messages"


class LocalizedTextKey:
    WELCOME = "welcome"
    SENT_TO_STAFF = "sent_to_staff"
    USERNAME_REQUIRED = "username_required"
    WELCOME_MEMBER = "welcome_member"
    WELCOME_NOT_MEMBER = "welcome_not_member"
    SEND_OTHER_MEMBERS = "send_other_members"
    SEND_SOCIAL = "send_social"
    DESCRIBE_SELF = "describe_self"
    DESCRIBE_SELF_SEND_MORE = "describe_self_send_more"
    APPLICATION_CANCELED = "application_canceled"
    APPLICATION_TIMEOUT = "application_timeout"
    APPLICATION_NOT_READY = "application_not_ready"
    APPLICATION_SENT_TO_STAFF = "application_sent_to_staff"
    APPLICATION_ACCEPTED = "application_accepted"
    APPLICATION_REJECTED_ANSWER = "application_rejected_answer"


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
    # LocalizedTextKey.USERNAME_REQUIRED: dict(
    #     label="username necessario",
    #     explanation="Il messaggio che verrà inviato agli utenti se non hanno impostato uno username",
    #     emoji=Emoji.SIGN,
    #     show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    # ),
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
    LocalizedTextKey.DESCRIBE_SELF_SEND_MORE: dict(
        label="presentazione (invia altro)",
        explanation="Il messaggio con cui il bot dirà all'utente che può inviare altri messaggi per presentarsi",
        emoji=Emoji.PLUS,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.APPLICATION_CANCELED: dict(
        label="richiesta annullata",
        explanation="Il messaggio che verrà inviato all'utente se annulla la procedura di richiesta",
        emoji=Emoji.CANCEL,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.APPLICATION_TIMEOUT: dict(
        label="timeout richiesta",
        explanation="Il messaggio che verrà inviato all'utente se non completa la richiesta nel tempo prestabilito",
        emoji=Emoji.ALARM,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.APPLICATION_SENT_TO_STAFF: dict(
        label="richiesta inviata",
        explanation="Il messaggio che verrà inviato all'utente dopo che invia la richiesta",
        emoji=Emoji.ENVELOPE,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.APPLICATION_NOT_READY: dict(
        label="richiesta incompleta",
        explanation="Il messaggio che verrà inviato all'utente se cerca di inviare una richiesta incompleta "
                    "(tipo senza alcun messaggio di testo)",
        emoji=Emoji.QUESTION,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.APPLICATION_ACCEPTED: dict(
        label="richiesta accettata",
        explanation="Il messaggio che verrà inviato all'utente quando la sua richiesta viene accettata da un admin",
        emoji=Emoji.DONE,
        show_if_true_bot_setting_key=BotSettingKey.APPROVAL_MODE
    ),
    LocalizedTextKey.APPLICATION_REJECTED_ANSWER: dict(
        label="risposta ai rifiutati",
        explanation="Il messaggio che verrà inviato come risposta agli utenti rifiutati quando usano /start",
        emoji=Emoji.EVIL,
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

BOT_SETTINGS_CATEGORIES_METADATA = {
    BotSettingCategory.GENERAL: dict(
        emoji=Emoji.GEAR,
        label="general"
    ),
    BotSettingCategory.USER_MESSAGES: dict(
        emoji=Emoji.PERSON,
        label="user messages"
    ),
    BotSettingCategory.REQUESTS: dict(
        emoji=Emoji.PEACE,
        label="richieste"
    ),
    BotSettingCategory.RADAR: dict(
        emoji=Emoji.COMPASS,
        label="radar"
    ),
    BotSettingCategory.PARTIES_LIST: dict(
        emoji=Emoji.ANNOUNCEMENT,
        label="lista feste"
    ),
}


BOT_SETTINGS_DEFAULTS = {
    BotSettingKey.SENT_TO_STAFF: dict(
        category=BotSettingCategory.USER_MESSAGES,
        default=True,
        label="\"sent to staff\" message",
        emoji=Emoji.ENVELOPE,
        description="when an user sends a message, tell them it has been sent to the staff",
        show_if_true_key=None,
        telegram_media=False
    ),
    BotSettingKey.BROADCAST_EDITS: dict(
        category=BotSettingCategory.USER_MESSAGES,
        default=True,
        label="broadcast edits",
        emoji=Emoji.PENCIL,
        description="edit staff messages sent to users when the original message in the staff chat is edited",
        show_if_true_key=None,
        telegram_media=False
    ),
    BotSettingKey.ALLOW_USER_REVOKE: dict(
        category=BotSettingCategory.USER_MESSAGES,
        default=True,
        label="user messages revoke",
        emoji=Emoji.TRASH,
        description="allow users to revoke the messages forwarded in the staff chat",
        show_if_true_key=None,
        telegram_media=False
    ),
    BotSettingKey.CHAT_INVITE_LINK: dict(
        category=BotSettingCategory.GENERAL,
        default=None,
        label="chat invite link",
        emoji=Emoji.LINK,
        description="the chat's invite link",
        show_if_true_key=None,
        telegram_media=False
    ),
    BotSettingKey.FALLBACK_LANGAUGE: dict(
        category=BotSettingCategory.GENERAL,
        default=Language.EN,
        label="fallback language",
        emoji=Emoji.EARTH,
        description="the language that should be used if the user language's version of a text is not available",
        show_if_true_key=None,
        telegram_media=False
    ),
    BotSettingKey.PARTIES_LIST: dict(
        category=BotSettingCategory.PARTIES_LIST,
        default=False,
        label="on/off",
        emoji=Emoji.DONE,
        description="ogni settimana, invia un messaggio nel canale con la lista delle feste imminenti",
        show_if_true_key=BotSettingKey.APPROVAL_MODE,
        telegram_media=False
    ),
    BotSettingKey.PARTIES_LIST_WEEKS: dict(
        category=BotSettingCategory.PARTIES_LIST,
        default=1,
        label="settimane",
        emoji=Emoji.CRYSTAL_SPHERE,
        description="quante settimane includere nella lista, 0 oppure 1 per la settimana corrente",
        show_if_true_key=BotSettingKey.APPROVAL_MODE,
        telegram_media=False
    ),
    BotSettingKey.PARTIES_LIST_UPDATE_ONLY: dict(
        category=BotSettingCategory.PARTIES_LIST,
        default=False,
        label="lista persistente",
        emoji=Emoji.RECYCLE,
        description="se abilitato, invece che inviare la lista delle feste ogni settimana, verrà aggiornato sempre lo stesso messaggio",
        show_if_true_key=BotSettingKey.APPROVAL_MODE,
        telegram_media=False
    ),
    BotSettingKey.PARTIES_LIST_WEEKDAY: dict(
        category=BotSettingCategory.PARTIES_LIST,
        default=3,  # 3: giovedì
        label="giorno settimana",
        emoji=Emoji.CALENDAR,
        description="che giorno della settimana re-inviare la lista, in numero (0: lunedì, ..., 6: domenica)",
        show_if_true_key=BotSettingKey.APPROVAL_MODE,
        telegram_media=False
    ),
    BotSettingKey.PARTIES_LIST_HOUR: dict(
        category=BotSettingCategory.PARTIES_LIST,
        default=20,
        label="ora",
        emoji=Emoji.CLOCK,
        description="a che ora inviare la lista",
        show_if_true_key=BotSettingKey.APPROVAL_MODE,
        telegram_media=False
    ),
    BotSettingKey.PARTIES_LIST_PIN: dict(
        category=BotSettingCategory.PARTIES_LIST,
        default=True,
        label="fissa messaggi",
        emoji=Emoji.PIN_2,
        description="se fissare o meno i messaggi con la lista delle feste dopo che vengono inviati",
        show_if_true_key=BotSettingKey.APPROVAL_MODE,
        telegram_media=False
    ),
    BotSettingKey.PARTIES_LIST_DISCUSSION_LINK: dict(
        category=BotSettingCategory.PARTIES_LIST,
        default=False,
        label="link messaggi gruppo",
        emoji=Emoji.PEOPLE,
        description="se i messaggi devono linkare, oltre ai post nel canale, anche il relativo post nel gruppo",
        show_if_true_key=BotSettingKey.APPROVAL_MODE,
        telegram_media=False
    ),
    BotSettingKey.APPROVAL_MODE: dict(
        category=BotSettingCategory.REQUESTS,
        default=False,
        label="approval mode",
        emoji=Emoji.LENS,
        description="approve/refuse users who are not in the users' group chat",
        show_if_true_key=None,
        telegram_media=False
    ),
    BotSettingKey.RABBIT_FILE: dict(
        category=BotSettingCategory.REQUESTS,
        default=None,
        label="\"follow the rabbit\"",
        emoji=Emoji.RABBIT,
        description="file da mandare agli utenti rifiutati",
        show_if_true_key=BotSettingKey.APPROVAL_MODE,
        telegram_media=True
    ),
    BotSettingKey.RADAR_FILE: dict(
        category=BotSettingCategory.RADAR,
        default=None,
        label="gif comando radar",
        emoji=Emoji.COMPASS,
        description="gif da mandare quando qualcuno usa /radar23",
        show_if_true_key=BotSettingKey.APPROVAL_MODE,
        telegram_media=True
    ),
}


class TempDataKey:
    FALLBACK_LANGUAGE = "default_language"
    LOCALIZED_TEXTS = "tmp_localized_text_data"
    BOT_SETTINGS = "tmp_bot_setting_data"
    APPLICATION_DATA = "application_data"
    APPLICATION_ID = "application_request_id"
    LOCALIZED_TEXTS_LAST_MESSAGE_ID = "localized_text_last_message_id"  # not temp, it is not supposed to be cleaned up
    BOT_SETTINGS_LAST_MESSAGE_ID = "bot_settings_last_message_id"
    DB_INSTANCES = "_database_instances"
    EVENTS_FILTERS = "events_filters"
    EVENTS_CACHE = "events_cache"
    EVENTS_CACHE_DATA = "events_cache_data"
    EVENTS_CACHE_SAVED_ON = "events_cache_saved_on"
    RADAR_DATE_OVERRIDE = "radar_date_override"
    RADAR_PROTECT_CONTENT_OVERRIDE = "radar_protect_content_override"
    FIRST_DIFF_TEXT = "first_diff_text"
    UPDATE_PARTIES_MESSAGE = "update_parties_message"
    FORCE_POST_PARTIES_MESSAGE = "force_post_parties_message"
    MUTE_EVENT_MESSAGE_BUTTON_ONCE = "mute_event_message_button_once"
    NOT_A_PARTY_MESSAGE_BUTTON_ONCE = "notaparty_event_message_button_once"
    DELETE_DUPLICATE_MESSAGE_BUTTON_ONCE = "delete_duplicate_message_button_once"
    SETTINGS_MESSAGE_TYPE = "settings_message_type"


COMMAND_PREFIXES = ["/", "!"]

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
    WAITING_NEW_SETTING_VALUE_MEDIA = 30


class Group:
    DEBUG = 1
    PREPROCESS = 3
    NORMAL = 5
    POSTPROCESS = 10


class Regex:
    FIRST_LINE = r"^(.+)$"
    USER_ID_HASHTAG = r"(?:#user|#id)(?P<user_id>\d+)"
    USER_ID_HASHTAG_SUB = r"((?:#user|#id)\d+)"
    DATETIME = r"(?P<date>(?P<day>\d{1,2})[/.-](?P<month>\d{1,2})(?:[/.-](?P<year>\d{2,4}))?)\s+((?P<hour>\d{1,2}):(?P<minute>\d{1,2})(?::(?P<second>\d{1,2}))?)"
    DATE = r"(?P<day>\d{1,2})[/.-](?P<month>\d{1,2})(?:[/.-](?P<year>\d{2,4}))?"
    # https://regex101.com/r/Exr6Km/3
    MESSAGE_LINK = r"^(?:https?://)?(?:www\.)?t(?:elegram)?\.(?:org|me|dog)/(?:c/(?P<chat_id>\d+)|(?P<username>[a-zA-Z](?:_(?!_)|[a-zA-Z0-9]){2,30}[a-zA-Z0-9]))(?:/(?P<topic_id>\d+))?(?:/(?P<message_id>\d+))"


class RegionHashtag:
    ALBANIA = "#albania"
    ALBANY = "#albany"
    ARGENTINA = "#argentina"
    NORD_ITALY = "#norditaly"
    CENTER_ITALY = "#centeritaly"
    CENTRO_ITALY = "#centroitaly"
    SUD_ITALY = "#suditaly"
    SARDEGNA = "#sardegna"
    SICILIA = "#sicilia"
    FRANCE = "#france"
    FRANCIA = "#francia"
    GERMANY = "#germany"
    GERMANIA = "#germania"
    SWISS = "#swiss"
    BELGIUM = "#belgium"
    BELGIO = "#belgio"
    SPAIN = "#spain"
    SPAGNA = "#spagna"
    NETHERLANDS = "#netherlands"
    NETHERLAND = "#netherland"
    NLD = "#nld"
    NL = "#nl"
    PORTUGAL = "#portugal"
    PORTOGALLO = "#portogallo"
    AUSTRIA = "#austria"
    ENGLAND = "#england"
    UK = "#uk"
    SCOTLAND = "#scotland"
    SCOZIA = "#scozia"
    CZECHIA = "#czechia"
    CZ = "#cz"
    REPUBBLICA_CECA = "#repubblicaceca"
    POLAND = "#poland"
    PL = "#pl"
    POLONIA = "#polonia"
    SLOVENIA = "#slovenia"
    SLOVAKIA = "#slovakia"
    ROMANIA = "#romania"
    RO = "#ro"
    CROATIA = "#croatia"
    CROAZIA = "#croazia"
    HUNGARY = "#hungary"
    UNGARIA = "#ungaria"
    BULGARIA = "#bulgaria"
    GREECE = "#greece"
    GRECIA = "#grecia"
    DENMARK = "#denmark"
    DANIMARCA = "#danimarca"
    MOROCCO = "#morocco"
    MAROCCO = "#marocco"
    SWEDEN = "#sweden"
    SVEZIA = "#svezia"
    NORWAY = "#norway"
    NORVEGIA = "#norvegia"
    COLOMBIA = "#colombia"
    FINLAND = "#finland"
    FINLANDIA = "#finlandia"
    CHILE = "#chile"
    CILE = "#cile"
    ITALIA = "#italia"
    ITALY = "#italy"
    IRELAND = "#ireland"
    IRLANDA = "#irlanda"
    EUROPE = "#europe"
    EUROPA = "#europa"
    AROUND_THE_WORLD = "#aroundtheworld"


class RegionName:
    ALBANIA = "Albania"
    ARGENTINA = "Argentina"
    AUSTRIA = "Austria"
    BELGIO = "Belgio"
    BULGARIA = "Bulgaria"
    CENTRO_ITALIA = "Centro Italia"
    CILE = "Cile"
    COLOMBIA = "Colombia"
    CROAZIA = "Croazia"
    DANIMARCA = "Danimarca"
    EUROPA = "Europa"
    FINLANDIA = "Finlandia"
    FRANCIA = "Francia"
    GERMANIA = "Germania"
    GRECIA = "Grecia"
    INGHILTERRA = "Inghilterra"
    IRLANDA = "Irlanda"
    ITALIA = "Italia"
    MAROCCO = "Marocco"
    NORD_ITALIA = "Nord Italia"
    NORVEGIA = "Norvegia"
    PAESI_BASSI = "Paesi Bassi"
    POLONIA = "Polonia"
    PORTOGALLO = "Portogallo"
    REPUBBLICA_CECA = "Repubblica Ceca"
    RESTO_DEL_MONDO = "Resto del Mondo"
    ROMANIA = "Romania"
    SARDEGNA = "Sardegna"
    SCOZIA = "Scozia"
    SICILIA = "Sicilia"
    SLOVACCHIA = "Slovacchia"
    SLOVENIA = "Slovenia"
    SPAGNA = "Spagna"
    SUD_ITALIA = "Sud Italia"
    SVEZIA = "Svezia"
    SVIZZERA = "Svizzera"
    UNGARIA = "Ungaria"


REGIONS_DATA = {
    RegionName.ALBANIA: dict(hashtags=[RegionHashtag.ALBANIA, RegionHashtag.ALBANY], emoji=Flag.ALBANY),
    RegionName.ARGENTINA: dict(hashtags=[RegionHashtag.ARGENTINA], emoji=Flag.ARGENTINA),
    RegionName.AUSTRIA: dict(hashtags=[RegionHashtag.AUSTRIA], emoji=Flag.AUSTRIA),
    RegionName.BELGIO: dict(hashtags=[RegionHashtag.BELGIUM, RegionHashtag.BELGIO], emoji=Flag.BELGIUM),
    RegionName.BULGARIA: dict(hashtags=[RegionHashtag.BULGARIA], emoji=Flag.BULGARIA),
    RegionName.CENTRO_ITALIA: dict(hashtags=[RegionHashtag.CENTER_ITALY, RegionHashtag.CENTRO_ITALY], emoji=Flag.ITALY),
    RegionName.CILE: dict(hashtags=[RegionHashtag.CILE, RegionHashtag.CHILE], emoji=Flag.CHILE),
    RegionName.COLOMBIA: dict(hashtags=[RegionHashtag.COLOMBIA], emoji=Flag.COLOMBIA),
    RegionName.CROAZIA: dict(hashtags=[RegionHashtag.CROATIA, RegionHashtag.CROAZIA], emoji=Flag.CROATIA),
    RegionName.DANIMARCA: dict(hashtags=[RegionHashtag.DENMARK, RegionHashtag.DANIMARCA], emoji=Flag.DENMARK),
    RegionName.FINLANDIA: dict(hashtags=[RegionHashtag.FINLAND, RegionHashtag.FINLANDIA], emoji=Flag.FINLAND),
    RegionName.FRANCIA: dict(hashtags=[RegionHashtag.FRANCE, RegionHashtag.FRANCIA], emoji=Flag.FRANCE),
    RegionName.GERMANIA: dict(hashtags=[RegionHashtag.GERMANY, RegionHashtag.GERMANIA], emoji=Flag.GERMANY),
    RegionName.GRECIA: dict(hashtags=[RegionHashtag.GRECIA, RegionHashtag.GREECE], emoji=Flag.GREECE),
    RegionName.INGHILTERRA: dict(hashtags=[RegionHashtag.UK, RegionHashtag.ENGLAND], emoji=Flag.ENGLAND),
    RegionName.IRLANDA: dict(hashtags=[RegionHashtag.IRELAND, RegionHashtag.IRLANDA], emoji=Flag.IRELAND),
    RegionName.MAROCCO: dict(hashtags=[RegionHashtag.MAROCCO, RegionHashtag.MOROCCO], emoji=Flag.MOROCCO),
    RegionName.NORD_ITALIA: dict(hashtags=[RegionHashtag.NORD_ITALY], emoji=Flag.ITALY),
    RegionName.NORVEGIA: dict(hashtags=[RegionHashtag.NORWAY, RegionHashtag.NORVEGIA], emoji=Flag.NORWAY),
    RegionName.PAESI_BASSI: dict(hashtags=[RegionHashtag.NETHERLANDS, RegionHashtag.NETHERLAND, RegionHashtag.NLD, RegionHashtag.NL], emoji=Flag.NETHERLANDS),
    RegionName.POLONIA: dict(hashtags=[RegionHashtag.POLAND, RegionHashtag.POLONIA, RegionHashtag.PL], emoji=Flag.POLAND),
    RegionName.PORTOGALLO: dict(hashtags=[RegionHashtag.PORTUGAL, RegionHashtag.PORTOGALLO], emoji=Flag.PORTUGAL),
    RegionName.REPUBBLICA_CECA: dict(hashtags=[RegionHashtag.CZ, RegionHashtag.CZECHIA, RegionHashtag.REPUBBLICA_CECA], emoji=Flag.CZECH_REPUBLIC),
    RegionName.ROMANIA: dict(hashtags=[RegionHashtag.ROMANIA, RegionHashtag.RO], emoji=Flag.ROMANIA),
    RegionName.SARDEGNA: dict(hashtags=[RegionHashtag.SARDEGNA], emoji=Flag.ITALY),
    RegionName.SCOZIA: dict(hashtags=[RegionHashtag.SCOTLAND, RegionHashtag.SCOZIA], emoji=Flag.SCOTLAND),
    RegionName.SICILIA: dict(hashtags=[RegionHashtag.SICILIA], emoji=Flag.ITALY),
    RegionName.SLOVACCHIA: dict(hashtags=[RegionHashtag.SLOVAKIA], emoji=Flag.SLOVAKIA),
    RegionName.SLOVENIA: dict(hashtags=[RegionHashtag.SLOVENIA], emoji=Flag.SLOVENIA),
    RegionName.SPAGNA: dict(hashtags=[RegionHashtag.SPAIN, RegionHashtag.SPAGNA], emoji=Flag.SPAIN),
    RegionName.SVIZZERA: dict(hashtags=[RegionHashtag.SWISS], emoji=Flag.SWISS),
    RegionName.SUD_ITALIA: dict(hashtags=[RegionHashtag.SUD_ITALY], emoji=Flag.ITALY),
    RegionName.SVEZIA: dict(hashtags=[RegionHashtag.SVEZIA, RegionHashtag.SWEDEN], emoji=Flag.SWEDEN),
    RegionName.UNGARIA: dict(hashtags=[RegionHashtag.UNGARIA, RegionHashtag.HUNGARY], emoji=Flag.HUNGARY),
    # these needs to be placed *below* their sub-regions
    RegionName.EUROPA: dict(hashtags=[RegionHashtag.EUROPA, RegionHashtag.EUROPE], emoji=Flag.EUROPE),
    RegionName.ITALIA: dict(hashtags=[RegionHashtag.ITALY, RegionHashtag.ITALIA], emoji=Flag.ITALY),
    RegionName.RESTO_DEL_MONDO: dict(hashtags=[RegionHashtag.AROUND_THE_WORLD], emoji=Flag.AROUND_THE_WORLD),
}
