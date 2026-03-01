import re

from dorasuper.emoji import (
    E_ADMIN, E_AFK, E_ANDROID, E_BACK, E_BELL, E_BOT, E_CALENDAR, E_CAMERA,
    E_LIMIT, E_PIN_LOC, E_RECYCLE, E_RIGHT_ARROW,
    E_CHECK, E_CLOCK, E_COFFEE, E_CROSS, E_DART, E_DOWNLOAD, E_ERROR,
    E_FIRE, E_GEAR, E_GIFT, E_GLOBE, E_GROUP, E_HEART, E_HOME, E_ID,
    E_IMAGE, E_INFO, E_IOS, E_KEY, E_LINK, E_LIST, E_LOADING, E_LOCK,
    E_MEDAL, E_MEGAPHONE, E_MENU, E_MSG, E_MUSIC, E_NEXT, E_NOTE,
    E_PARTY, E_PHOTO, E_PIN, E_QUESTION, E_ROCKET, E_SEARCH, E_SHIELD,
    E_SOS, E_SPARKLE, E_STAR, E_STAT, E_SUCCESS, E_TAG, E_TIP, E_USER,
    E_UPLOAD, E_VN, E_VIP, E_VIP1, E_WAIT, E_WARN, E_WELCOME, E_WRENCH,
)

EMOJI_FMT = {
    "E_ADMIN": E_ADMIN, "E_AFK": E_AFK, "E_ANDROID": E_ANDROID, "E_BACK": E_BACK,
    "E_BELL": E_BELL, "E_BOT": E_BOT, "E_CALENDAR": E_CALENDAR, "E_CAMERA": E_CAMERA,
    "E_CHECK": E_CHECK, "E_CLOCK": E_CLOCK, "E_COFFEE": E_COFFEE, "E_CROSS": E_CROSS,
    "E_DART": E_DART, "E_DOWNLOAD": E_DOWNLOAD, "E_ERROR": E_ERROR, "E_FIRE": E_FIRE,
    "E_GEAR": E_GEAR, "E_GIFT": E_GIFT, "E_GLOBE": E_GLOBE, "E_GROUP": E_GROUP,
    "E_HEART": E_HEART, "E_HOME": E_HOME, "E_ID": E_ID, "E_IMAGE": E_IMAGE,
    "E_INFO": E_INFO, "E_IOS": E_IOS, "E_KEY": E_KEY, "E_LINK": E_LINK, "E_LIMIT": E_LIMIT, "E_LIST": E_LIST, "E_LOADING": E_LOADING, "E_LOCK": E_LOCK, "E_MEDAL": E_MEDAL,
    "E_MEGAPHONE": E_MEGAPHONE, "E_MENU": E_MENU, "E_MSG": E_MSG, "E_MUSIC": E_MUSIC,
    "E_NEXT": E_NEXT, "E_NOTE": E_NOTE, "E_PARTY": E_PARTY, "E_PHOTO": E_PHOTO,
    "E_PIN": E_PIN, "E_PIN_LOC": E_PIN_LOC, "E_QUESTION": E_QUESTION,
    "E_RECYCLE": E_RECYCLE, "E_RIGHT_ARROW": E_RIGHT_ARROW, "E_ROCKET": E_ROCKET, "E_SEARCH": E_SEARCH,
    "E_SHIELD": E_SHIELD, "E_SOS": E_SOS, "E_SPARKLE": E_SPARKLE, "E_STAR": E_STAR,
    "E_STAT": E_STAT, "E_SUCCESS": E_SUCCESS, "E_TAG": E_TAG, "E_TIP": E_TIP,
    "E_USER": E_USER, "E_UPLOAD": E_UPLOAD, "E_VN": E_VN, "E_VIP": E_VIP, "E_VIP1": E_VIP1,
    "E_WAIT": E_WAIT, "E_WARN": E_WARN, "E_WELCOME": E_WELCOME, "E_WRENCH": E_WRENCH,
}


def _strip_emoji_for_btn(s):
    """Remove all emoji from string for button labels."""
    if not isinstance(s, str):
        return s
    s = re.sub(r'<emoji id="[^"]+">(.+?)</emoji>', "", s)
    s = re.sub(r'<tg-emoji emoji-id="[^"]+">(.+?)</tg-emoji>', "", s)
    return s


EMOJI_FMT_BTN = {k: _strip_emoji_for_btn(v) for k, v in EMOJI_FMT.items()}
