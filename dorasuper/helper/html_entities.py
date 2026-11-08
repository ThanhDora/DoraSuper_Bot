"""Parse a small HTML subset plus official <tg-emoji> tags into Telegram entities."""
import html
import re

from pyrogram import enums
from pyrogram.types import MessageEntity

from dorasuper.tg_emoji import EMOJI_TAG, premium_enabled


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def strip_custom_emoji_entities(entities):
    if not entities:
        return []
    return [
        e for e in entities
        if getattr(e, "type", None) != enums.MessageEntityType.CUSTOM_EMOJI
    ]


def html_to_entities(html_text: str):
    """Parse HTML subset + custom emoji to (text, entities)."""
    html_text = html_text or ""
    entities = []
    out = []
    out_len = 0
    stack = []

    i = 0
    while i < len(html_text):
        if html_text[i] == "<":
            m = EMOJI_TAG.match(html_text, i)
            if m:
                fallback = html.unescape(m["alt"]).strip() or "•"
                out.append(fallback)
                length = utf16_len(fallback)
                if premium_enabled():
                    entities.append(MessageEntity(
                        type=enums.MessageEntityType.CUSTOM_EMOJI,
                        offset=out_len, length=length,
                        custom_emoji_id=int(m["id"]),
                    ))
                out_len += length
                i = m.end()
                continue

            if html_text.startswith("<a", i):
                m = re.match(r'<a\s+href="([^"]+)">', html_text[i:], re.IGNORECASE)
                if m:
                    url = html.unescape(m.group(1))
                    stack.append(("a", out_len, url))
                    i += m.end()
                    continue
            if html_text.startswith("</a>", i):
                if stack and stack[-1][0] == "a":
                    _, start, url = stack.pop()
                    length = out_len - start
                    if length > 0:
                        entities.append(
                            MessageEntity(
                                type=enums.MessageEntityType.TEXT_LINK,
                                offset=start,
                                length=length,
                                url=url,
                            )
                        )
                i += len("</a>")
                continue

            m = re.match(r"<(/?)(b|i|code)>", html_text[i:], re.IGNORECASE)
            if m:
                closing = m.group(1) == "/"
                tag = m.group(2).lower()
                if not closing:
                    stack.append((tag, out_len, None))
                else:
                    if stack and stack[-1][0] == tag:
                        _, start, _ = stack.pop()
                        length = out_len - start
                        if length > 0:
                            ent_type = {
                                "b": enums.MessageEntityType.BOLD,
                                "i": enums.MessageEntityType.ITALIC,
                                "code": enums.MessageEntityType.CODE,
                            }[tag]
                            entities.append(
                                MessageEntity(type=ent_type, offset=start, length=length)
                            )
                i += m.end()
                continue

            out.append("<")
            out_len += utf16_len("<")
            i += 1
            continue

        next_lt = html_text.find("<", i)
        chunk = html_text[i:] if next_lt == -1 else html_text[i:next_lt]
        i = len(html_text) if next_lt == -1 else next_lt
        if chunk:
            chunk = html.unescape(chunk)
            out.append(chunk)
            out_len += utf16_len(chunk)

    return "".join(out), entities
