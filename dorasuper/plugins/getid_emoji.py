# Lệnh /getid, /getemoji: xem Chat ID, User ID; reply tin có custom emoji để lấy emoji ID.

import logging
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message

from dorasuper import app
from dorasuper.emoji import E_ID, E_USER, E_WARN
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")

__MODULE__ = "GetID"
__HELP__ = "<blockquote>/getid — Xem Chat ID, User ID (trả lời tin nhắn để xem ID người đó).\n/getemoji — <b>Bắt buộc reply</b> tin nhắn có emoji premium/custom → bot trả lại <b>emoji ID</b> (số, chạm để copy).</blockquote>"


@app.on_message(filters.command(["getid", "getemoji"], COMMAND_HANDLER))
async def getid_cmd(_, ctx: Message):
    cmd = (ctx.command or ["getid"])[0].lower()
    is_getemoji = cmd == "getemoji"

    # /getemoji bắt buộc phải reply tin nhắn có emoji
    if is_getemoji and not ctx.reply_to_message:
        await ctx.reply_msg(
            f"{E_WARN} <b>Vui lòng trả lời (reply) tin nhắn có chứa emoji</b> muốn lấy ID.\n\nGửi /getemoji khi đang reply đúng tin có emoji premium/custom.",
            parse_mode=enums.ParseMode.HTML,
        )
        return

    # Có reply → xử lý tin được trả lời
    if ctx.reply_to_message:
        msg = ctx.reply_to_message
        entities = list(msg.entities or []) + list(msg.caption_entities or [])
        custom = [
            e for e in entities
            if getattr(e, "type", None) == enums.MessageEntityType.CUSTOM_EMOJI
        ]
        if not custom:
            # /getemoji mà tin reply không có emoji → nhắc reply đúng tin có emoji
            if is_getemoji:
                await ctx.reply_msg(
                    f"{E_WARN} Tin nhắn được trả lời <b>không chứa emoji</b> premium/custom.\n\nVui lòng reply đúng tin nhắn có emoji muốn lấy ID.",
                    parse_mode=enums.ParseMode.HTML,
                )
                return
            # /getid: không có emoji → gửi User ID người được trả lời + Chat ID
            target = msg.from_user
            if not target:
                await ctx.reply_msg(f"{E_WARN} Không lấy được thông tin từ tin nhắn.", parse_mode=enums.ParseMode.HTML)
                return
            name = f"{(target.first_name or '')} {(target.last_name or '')}".strip() or "—"
            text = (
                f"{E_USER} <b>User:</b> {name}\n"
                f"{E_ID} <b>User ID:</b> <code>{target.id}</code>\n"
                f"{E_ID} <b>Chat ID:</b> <code>{ctx.chat.id}</code>"
            )
            await ctx.reply_msg(text, parse_mode=enums.ParseMode.HTML)
            return
        # Có custom emoji → chỉ gửi ID (số), mỗi dòng một ID để chạm copy
        code_parts = []
        for e in custom:
            eid = getattr(e, "custom_emoji_id", None) or getattr(e, "document_id", None)
            if eid is None:
                continue
            code_parts.append(f"<code>{eid}</code>")
        text = "📋 <b>Emoji ID</b> — chạm để copy:\n\n" + "\n".join(code_parts)
        await ctx.reply_msg(text, parse_mode=enums.ParseMode.HTML)
        return

    # Không reply + /getid → gửi Chat ID + User ID của bạn
    target = ctx.from_user
    if not target:
        await ctx.reply_msg(f"{E_WARN} Không lấy được thông tin.", parse_mode=enums.ParseMode.HTML)
        return
    name = f"{(target.first_name or '')} {(target.last_name or '')}".strip() or "—"
    text = (
        f"{E_USER} <b>User:</b> {name}\n"
        f"{E_ID} <b>User ID:</b> <code>{target.id}</code>\n"
        f"{E_ID} <b>Chat ID:</b> <code>{ctx.chat.id}</code>"
    )
    await ctx.reply_msg(text, parse_mode=enums.ParseMode.HTML)
