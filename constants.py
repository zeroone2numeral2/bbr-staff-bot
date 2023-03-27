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


class Language:
    EN = "en"
    IT = "it"
    FR = "fr"
    ES = "es"


ADMIN_HELP = """<b>Admin commands (private)</b>:
- <code>/welcome [welcome text]</code>:  set the welcome text for a specific language (the bot will ask you which one \
later)
- <code>/welcome</code>: see or delete a langauge's welcome text
- <code>/placeholders</code>: list available placeholders (they can be used in welcome texts)

<b>Admin commands (staff chat)</b>:
- <code>/setstaff</code>: use the current chat as staff chat
- <code>/reloadadmins</code>: update the staff chat's admins list
- <code>/ban [reason]</code>: ban an user from using the bot. The bot will tell the user they are banned 
when they send new messages. The reason is optional
- <code>/shadowban [reason]</code>: like <code>/ban</code>, but the user won't know they were banned

<b>Things to keep in mind</b>
- an admin is whoever is an administrator in the current staff chat. Admins are updated as soon as they are changed, \
but <code>/reloadadmins</code> can be used to force-refresh the admins list
- <i>anyone</i> in the admins chat is allowed to reply to users, but only admins can ban them
"""
