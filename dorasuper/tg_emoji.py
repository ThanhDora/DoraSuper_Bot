"""Official Telegram custom emoji entities and keyboard icons.

Both legacy <emoji id> and Bot API <tg-emoji emoji-id> input are accepted.
Tags are a local formatting syntax: Telegram receives entities/style, never HTML
inside a button label. This module has no bot/config/database startup side effects.
"""
import html
import os
import re
import sys
from copy import copy
from functools import wraps

EMOJI_TAG = re.compile(
    r'<(?P<tag>emoji|tg-emoji)\s+(?:id|emoji-id)\s*=\s*[\"\'](?P<id>\d+)[\"\'][^>]*>'
    r'(?P<alt>[^<]*)</(?P=tag)\s*>', re.IGNORECASE,
)


def premium_enabled():
    # vars is already loaded during normal startup (including config.env).
    config = sys.modules.get("dorasuper.vars")
    if config is not None and hasattr(config, "USE_PREMIUM_EMOJI"):
        return config.USE_PREMIUM_EMOJI
    return os.environ.get("USE_PREMIUM_EMOJI", "true").strip().lower() in ("1", "true", "yes")


def to_html(text):
    """Canonicalize both input forms without changing ids or fallback text."""
    return EMOJI_TAG.sub(
        lambda m: f'<tg-emoji emoji-id="{m["id"]}">{m["alt"]}</tg-emoji>', str(text),
    )


def to_unicode(text):
    return EMOJI_TAG.sub(lambda m: m["alt"], str(text))


def split_button(text):
    text = str(text)
    match = EMOJI_TAG.search(text)
    if not premium_enabled():
        return html.unescape(to_unicode(text)).strip(), None
    if match is None:
        return text, None
    label = html.unescape(EMOJI_TAG.sub("", text)).strip()
    # Telegram forbids empty labels; an icon-only button keeps an invisible label.
    return label or "\u2060", match["id"]


def emoji_error(error):
    """Only retry known rejected emoji requests, never transport/time-out errors."""
    from pyrogram.errors import RPCError
    return isinstance(error, RPCError) and any(token in str(error).upper() for token in (
        "BUTTON_ICON_INVALID", "CUSTOM_EMOJI_INVALID", "DOCUMENT_INVALID",
        "ENTITY_TEXT_INVALID", "PREMIUM_ACCOUNT_REQUIRED", "PREMIUM_REQUIRED",
        "INPUT_CONSTRUCTOR_INVALID",
    ))


def plain_markup(markup):
    """Copy high-level inline markup, preserving button actions and labels."""
    if markup is None or not hasattr(markup, "inline_keyboard"):
        return markup
    result = copy(markup)
    result.inline_keyboard = []
    for row in markup.inline_keyboard:
        new_row = []
        for button in row:
            button = copy(button)
            button.icon_custom_emoji_id = None
            new_row.append(button)
        result.inline_keyboard.append(new_row)
    return result


def _plain_request(value):
    """Copy only changed TL branches, stripping icons and custom entities.

    Works for text/captions, media groups, inline results and markup-only edits.
    This keeps bold/link offsets and every callback/url payload unchanged.
    """
    from pyrogram import raw
    from pyrogram.raw.core import TLObject
    from .tg_keyboard import without_style
    if isinstance(value, (list, tuple)):
        result = []
        changed = False
        for item in value:
            if isinstance(item, raw.types.MessageEntityCustomEmoji):
                changed = True
                continue
            new = _plain_request(item)
            changed |= new is not item
            result.append(new)
        return result if changed else value
    if not isinstance(value, TLObject):
        return value
    result = value
    if getattr(value, "style", None) is not None:
        result = without_style(value)
    for key in value.__slots__:
        if key == "style":
            continue
        old = getattr(value, key, None)
        new = _plain_request(old)
        if new is not old:
            if result is value:
                result = copy(value)
            setattr(result, key, new)
    return result


def install():
    """Idempotent, process-local patches for the pinned older pyrofork."""
    from pyrogram import Client, types
    from pyrogram.parser.html import Parser, HTML
    from .tg_keyboard import install_raw_types, with_icon
    if getattr(Parser, "_dora_official_emoji", False):
        return
    install_raw_types()
    start, end, unparse = Parser.handle_starttag, Parser.handle_endtag, HTML.unparse

    def handle_starttag(self, tag, attrs):
        if tag in ("emoji", "tg-emoji"):
            if not premium_enabled():
                return
            attrs = dict(attrs)
            value = attrs.get("emoji-id") if tag == "tg-emoji" else attrs.get("id")
            if not value or not value.isdigit():
                return
            return start(self, "emoji", [("id", value)])
        return start(self, tag, attrs)

    def handle_endtag(self, tag):
        return end(self, "emoji" if tag == "tg-emoji" else tag)

    Parser.handle_starttag = handle_starttag
    Parser.handle_endtag = handle_endtag
    HTML.unparse = staticmethod(lambda text, entities: to_html(unparse(text, entities)))

    button_cls = types.InlineKeyboardButton
    init, write, read = button_cls.__init__, button_cls.write, button_cls.read

    @wraps(init)
    def button_init(self, text, *args, icon_custom_emoji_id=None, **kwargs):
        label, extracted = split_button(text)
        init(self, label, *args, **kwargs)
        self.icon_custom_emoji_id = str(icon_custom_emoji_id or extracted) if (
            premium_enabled() and (icon_custom_emoji_id or extracted)
        ) else None

    @wraps(write)
    async def button_write(self, client):
        button = await write(self, client)
        icon = getattr(self, "icon_custom_emoji_id", None)
        return with_icon(button, icon) if icon and premium_enabled() else button

    def button_read(button):
        result = read(button)
        if result is not None:
            icon = getattr(getattr(button, "style", None), "icon", None)
            result.icon_custom_emoji_id = str(icon) if icon is not None else None
        return result

    button_cls.__init__ = button_init
    button_cls.write = button_write
    button_cls.read = staticmethod(button_read)
    invoke = Client.invoke

    @wraps(invoke)
    async def safe_invoke(self, query, *args, **kwargs):
        return await invoke_with_fallback(invoke, self, query, *args, **kwargs)

    Client.invoke = safe_invoke
    Parser._dora_official_emoji = True


async def invoke_with_fallback(invoke, client, query, *args, **kwargs):
    if not premium_enabled():
        query = _plain_request(query)
    try:
        return await invoke(client, query, *args, **kwargs)
    except Exception as exc:
        if not emoji_error(exc):
            raise
        fallback = _plain_request(query)
        if fallback is query:
            raise
        return await invoke(client, fallback, *args, **kwargs)
