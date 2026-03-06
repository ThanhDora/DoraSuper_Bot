# Helper gửi/sửa tin nhắn an toàn: thử custom emoji trước, lỗi thì fallback Unicode.
# Tránh ENTITY_TEXT_INVALID / DocumentInvalid khi dùng E_* từ dorasuper.emoji.

import asyncio
import re
from typing import TYPE_CHECKING, Any, Optional

from pyrogram import enums
from pyrogram.types import Message

if TYPE_CHECKING:
    pass


def emoji_to_unicode(text: str) -> str:
    """Chuyển <emoji id="...">...</emoji> → Unicode (fallback khi emoji động lỗi)."""
    return re.sub(r'<emoji id="[^"]+">(.+?)</emoji>', r'\1', str(text))


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
    try:
        sent = await message.reply_text(text, **kwargs)
    except Exception:
        sent = await message.reply_text(emoji_to_unicode(text), **kwargs)
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
    try:
        return await msg.edit_text(text, **kwargs)
    except Exception:
        return await msg.edit_text(emoji_to_unicode(text), **kwargs)
