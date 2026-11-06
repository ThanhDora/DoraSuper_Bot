# Helper gửi/sửa tin nhắn an toàn: thử custom emoji trước, lỗi thì fallback Unicode.
# Tránh ENTITY_TEXT_INVALID / DocumentInvalid khi dùng E_* từ dorasuper.emoji.

import asyncio
from typing import Any, Optional

from pyrogram import enums
from pyrogram.types import Message

from dorasuper.tg_emoji import (
    to_unicode as emoji_to_unicode,
    to_html,
    plain_markup,
    emoji_error,
    premium_enabled,
)

def _fallback_kwargs(kwargs):
    kwargs = kwargs.copy()
    if "reply_markup" in kwargs:
        kwargs["reply_markup"] = plain_markup(kwargs["reply_markup"])
    if kwargs.get("entities"):
        kwargs["entities"] = [
            e for e in kwargs["entities"]
            if e.type != enums.MessageEntityType.CUSTOM_EMOJI
        ]
    return kwargs


async def reply_safe(
    message: Message,
    text: str,
    del_in: Optional[int] = None,
    **kwargs: Any,
) -> Optional[Message]:
    """
    Gửi tin: thử emoji động trước, lỗi thì gửi Unicode.
    Nếu del_in > 0 thì tự xóa tin sau del_in giây.
    """
    kwargs.setdefault("parse_mode", enums.ParseMode.HTML)
    del_in = kwargs.pop("del_in", del_in)
    text = to_html(text) if premium_enabled() else emoji_to_unicode(text)
    try:
        sent = await message.reply_text(text, **kwargs)
    except Exception as exc:
        if not emoji_error(exc):
            raise
        sent = await message.reply_text(emoji_to_unicode(text), **_fallback_kwargs(kwargs))
    if del_in and sent:
        async def _del():
            await asyncio.sleep(del_in)
            try:
                await sent.delete()
            except Exception:
                pass
        asyncio.create_task(_del())
    return sent


async def edit_safe(msg: Message, text: str, **kwargs: Any) -> Optional[Message]:
    """Sửa tin: thử emoji động trước, lỗi thì sửa bằng Unicode."""
    kwargs.setdefault("parse_mode", enums.ParseMode.HTML)
    text = to_html(text) if premium_enabled() else emoji_to_unicode(text)
    try:
        return await msg.edit_text(text, **kwargs)
    except Exception as exc:
        if not emoji_error(exc):
            raise
        return await msg.edit_text(emoji_to_unicode(text), **_fallback_kwargs(kwargs))
