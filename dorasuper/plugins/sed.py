import html

import regex
import logging
from logging import getLogger
from pyrogram import Client, filters
from pyrogram.errors import MessageEmpty
from pyrogram.types import Message

from dorasuper import app
from dorasuper.emoji import E_ERROR, E_TIP, E_WARN

LOGGER = getLogger("DoraSuper")

@app.on_message(filters.regex(r"^s/(.+)?/(.+)?(/.+)?") & filters.reply)
async def sed(self: Client, ctx: Message):
    exp = regex.split(r"(?<![^\\]\\)/", ctx.text)
    pattern = exp[1]
    replace_with = exp[2].replace(r"\/", "/")
    flags = exp[3] if len(exp) > 3 else ""

    rflags = 0

    count = 0 if "g" in flags else 1
    if "i" in flags and "s" in flags:
        rflags = regex.I | regex.S
    elif "i" in flags:
        rflags = regex.I
    elif "s" in flags:
        rflags = regex.S

    text = ctx.reply_to_message.text or ctx.reply_to_message.caption

    if not text:
        return

    try:
        res = regex.sub(
            pattern, replace_with, text, count=count, flags=rflags, timeout=1
        )
    except TimeoutError:
        return await ctx.reply_msg(f"{E_WARN} Biểu thức regex chạy quá lâu, vui lòng đơn giản hóa.")
    except regex.error as e:
        return await ctx.reply_msg(f"{E_WARN} Regex: {e}")
    else:
        try:
            await self.send_msg(
                ctx.chat.id,
                f"<pre>{html.escape(res)}</pre>",
                reply_to_message_id=ctx.reply_to_message.id,
            )
        except MessageEmpty:
            return await ctx.reply_msg(
                f"{E_TIP} Vui lòng trả lời tin nhắn để dùng tính năng này.", del_in=5
            )
        except Exception as e:
            return await ctx.reply_msg(f"{E_ERROR} Lỗi: {str(e)}")
