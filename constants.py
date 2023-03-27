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


class TempDataKey:
    WELCOME_LANGUAGE = "_welcome_language"


class Language:
    EN = "en"
    IT = "it"
    FR = "fr"
    ES = "es"


COMMAND_PREFIXES = ["/", "!", "."]

CACHE_TIME = 10

ADMIN_HELP = """<b><u>Admin commands (private)</u></b>:
- <code>/welcome</code>: see or edit a langauge's welcome text
- <code>/placeholders</code>: list available placeholders (they can be used in welcome texts)

<b><u>Admin commands (staff chat)</u></b>:
- <code>/setstaff</code>: use the current chat as staff chat
- <code>/reloadadmins</code>: update the staff chat's admins list

The following commands work in reply to an user's forwarded message in the staff chat:
- <code>/ban [reason]</code>: ban an user from using the bot. The bot will tell the user that they are banned 
when they send new messages. The reason is optional
- <code>/shadowban [reason]</code>: like <code>/ban</code>, but the user won't know they were banned
- <code>/unban</code>: unban the user
- <code>/info</code>: show everything we know about that user

<b><u>Things to keep in mind</u></b>
- an admin is whoever is an administrator in the current staff chat. Admins are updated as soon as they are added/removed, \
but <code>/reloadadmins</code> can be used to force-refresh the admins list
- <i>anyone</i> in the staff chat is allowed to reply to users or ban them
"""


class State:
    WAITING_WELCOME = 10
    WAITING_SENT_TO_STAFF_MESSAGE = 20
