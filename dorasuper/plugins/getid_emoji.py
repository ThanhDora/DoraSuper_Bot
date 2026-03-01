# Lệnh /getid, /getemoji: xem Chat ID, User ID; reply tin có custom emoji để lấy emoji ID.

import re
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message

from dorasuper import app
from dorasuper.emoji import E_ID, E_LIST, E_USER, E_WARN
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")

def _emoji_var_name(name: str) -> str:
    """Chuyển tên thành biến kiểu E_CEK: chỉ chữ, số, gạch dưới; viết hoa."""
    if not name or not name.strip():
        return ""
    s = re.sub(r"[^\w\s]", "", name.strip()).upper().replace(" ", "_")
    s = re.sub(r"_+", "_", s).strip("_")
    return f"E_{s}" if s else ""


__MODULE__ = "GetID"
__HELP__ = "<blockquote>/getid — Xem Chat ID, User ID (trả lời tin nhắn để xem ID người đó).\n/getemoji — <b>Bắt buộc reply</b> tin nhắn có emoji premium/custom → trả lại <b>emoji ID</b> (chạm để copy).\n/getemoji <b>Tên</b> — Reply tin có emoji + nhập tên (vd: Cek) → trả lại <b>code Python</b> dạng <code>E_CEK = '&lt;emoji id=\"...\"&gt;...&lt;/emoji&gt;'</code> để copy vào emoji.py.</blockquote>"


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
        # Lấy tên biến nếu user gửi /getemoji Tên (vd: /getemoji Cek → E_CEK)
        var_base = ""
        if is_getemoji and len(ctx.command) > 1:
            var_base = _emoji_var_name(" ".join(ctx.command[1:]))
        raw_text = (msg.text or msg.caption or "")
        emoji_entries = []
        for e in custom:
            eid = getattr(e, "custom_emoji_id", None) or getattr(e, "document_id", None)
            if eid is None:
                continue
            if raw_text and hasattr(e, "offset") and hasattr(e, "length"):
                try:
                    fallback = raw_text[e.offset : e.offset + e.length] or "•"
                except (IndexError, TypeError):
                    fallback = "•"
            else:
                fallback = "•"
            emoji_entries.append((eid, fallback))
        if not emoji_entries:
            await ctx.reply_msg(f"{E_WARN} Không lấy được emoji ID từ tin nhắn.", parse_mode=enums.ParseMode.HTML)
            return
        # Nếu có tên biến → trả về code Python để copy vào emoji.py
        if var_base:
            py_lines = []
            for i, (eid, fallback) in enumerate(emoji_entries):
                var = f"{var_base}_{i + 1}" if len(emoji_entries) > 1 else var_base
                fb_esc = fallback.replace("\\", "\\\\").replace("'", "\\'")
                # Chuỗi Python đúng format emoji.py
                line = f"{var} = '<emoji id=\"{eid}\">{fb_esc}</emoji>'"
                py_lines.append(line)
            code_block = "\n".join(py_lines)
            # Escape < > trong <pre> để Telegram không render thẻ <emoji>, copy ra đúng format
            code_block_esc = code_block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            preview_parts = []
            for i, (eid, fb) in enumerate(emoji_entries):
                v = f"{var_base}_{i + 1}" if len(emoji_entries) > 1 else var_base
                preview_parts.append(f'<emoji id="{eid}">{fb}</emoji>  <code>{v}</code>')
            text = (
                f"{E_LIST} <b>Code ID Emoji</b>:\n\n"
                f"<pre>{code_block_esc}</pre>\n\n"
                "Preview: " + "  ".join(preview_parts)
            )
        else:
            code_parts = [f'<emoji id="{eid}">{fb}</emoji>  <code>{eid}</code>' for eid, fb in emoji_entries]
            text = f"{E_LIST} <b>Code ID Emoji</b>:\n\n" + "\n".join(code_parts)
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
