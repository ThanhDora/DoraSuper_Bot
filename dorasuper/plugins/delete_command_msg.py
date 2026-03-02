# Plugin: xóa tin nhắn lệnh của user ngay sau khi bot đã reply.
# Chạy ở group=99 (sau mọi handler lệnh). Bot cần quyền xóa tin nhắn trong nhóm.

import asyncio
import re
from pyrogram import filters
from pyrogram.types import Message

from dorasuper import app
from dorasuper.vars import COMMAND_HANDLER

# Regex khớp mọi tin nhắn bắt đầu bằng prefix (/, !, ...) + tên lệnh
_prefixes = [p for p in (COMMAND_HANDLER or ["/"]) if p]
_prefix_re = "|".join(re.escape(p) for p in _prefixes) if _prefixes else re.escape("/")
COMMAND_ANY_RE = re.compile(r"^(" + _prefix_re + r")\s*(\S+)", re.IGNORECASE)

# Lệnh không tự động xóa tin nhắn (giữ để user tham chiếu hoặc bot cần reply_to_message)
NO_DELETE_COMMANDS = {
    "autodl", "dl", "tt", "tiktok",  # downloadsVideo
    "q", "r",  # quotly — cần reply để tạo sticker
    "kang", "unkang", "taosticker", "stickerid", "laysticker",  # stickers — cần reply
    "broadcast",  # reply để broadcast
    "summarize", "tomtat", "rewrite", "vietlai",  # ai reply
}


async def _is_command_msg(_, __, msg: Message):
    if not msg:
        return False
    m = COMMAND_ANY_RE.match((msg.text or msg.caption or "").strip())
    if not m:
        return False
    cmd = (m.group(2) or "").lower().split("@")[0]
    return cmd not in NO_DELETE_COMMANDS


is_command = filters.create(_is_command_msg)


@app.on_message(is_command, group=99)
async def delete_user_command_after_reply(_, msg: Message):
    try:
        await asyncio.sleep(0.15)  # Đợi bot reply gửi xong rồi mới xóa tin lệnh
        await msg.delete()
    except Exception:
        pass
