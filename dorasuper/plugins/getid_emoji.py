# Lệnh /getid, /getemoji: xem Chat ID, User ID; lấy ID của bất kì emoji/sticker nào (không chỉ premium/custom).

import re
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message

from dorasuper import app
from dorasuper.emoji import E_ID, E_USER, E_WARN
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
__HELP__ = (
    "<blockquote>/getid — Xem Chat ID, User ID (trả lời tin nhắn để xem ID người đó).\n"
    "/getemoji — Reply tin có emoji/sticker → trả <b>ID</b> (bất kì emoji, không chỉ premium/custom).\n"
    "/getemoji <b>Tên</b> — Có tên (vd: Cek) → trả thêm <b>code Python</b> để copy vào emoji.py.</blockquote>"
)


def _html_escape(s: str) -> str:
    """Escape cho HTML để bỏ vào blockquote."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _send_safe(chat_id, text, reply_to_id=None):
    """Gửi tin trong blockquote (HTML), nội dung đã escape để tránh ENTITY_TEXT_INVALID."""
    try:
        escaped = _html_escape(text)
        blockquote_text = f"<blockquote>{escaped}</blockquote>"
        await app.send_message(
            chat_id, blockquote_text,
            reply_to_message_id=reply_to_id,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        LOGGER.warning("getid_emoji _send_safe: %s", e)


@app.on_message(filters.command(["getid", "getemoji"], COMMAND_HANDLER), group=-1)
async def getid_cmd(_, ctx: Message):
    cmd = (ctx.command or ["getid"])[0].lower()
    is_getemoji = cmd == "getemoji"

    # /getemoji: bắt buộc reply
    if is_getemoji:
        try:
            if not ctx.reply_to_message:
                await _send_safe(ctx.chat.id, "⚠️ Vui lòng reply tin có emoji hoặc sticker rồi gửi /getemoji để lấy ID.", ctx.id)
                return
            msg = ctx.reply_to_message
            try:
                full = await app.get_messages(ctx.chat.id, msg.id)
                if isinstance(full, list):
                    full = full[0] if full else None
                if full:
                    msg = full
            except Exception:
                pass
            raw_text = (msg.text or msg.caption or "") or ""
            emoji_entries = []
            # 1) Entity có custom_emoji_id hoặc document_id (emoji trong text)
            entities = list(msg.entities or []) + list(msg.caption_entities or [])
            for e in entities:
                eid = getattr(e, "custom_emoji_id", None) or getattr(e, "document_id", None)
                if eid is None:
                    continue
                fallback = "•"
                if raw_text and hasattr(e, "offset") and hasattr(e, "length"):
                    try:
                        part = raw_text[e.offset : e.offset + e.length]
                        fallback = (part[0] if part else "•")
                    except (IndexError, TypeError):
                        pass
                emoji_entries.append((str(eid), fallback))
            # 2) Sticker: custom_emoji_id hoặc file_id, lấy emoji từ sticker
            if getattr(msg, "sticker", None):
                st = msg.sticker
                sid = getattr(st, "custom_emoji_id", None)
                fb = getattr(st, "emoji", None) or "•"
                if sid is not None:
                    emoji_entries.append((str(sid), fb))
                elif getattr(st, "file_id", None):
                    emoji_entries.append((st.file_id, fb))
            # 3) Emoji Unicode trong text (U+hex) nếu chưa có gì
            if not emoji_entries:
                raw = (msg.text or msg.caption or "") or ""
                if raw:
                    unicode_emojis = []
                    for ch in raw:
                        cp = ord(ch)
                        if (0x2600 <= cp <= 0x27BF) or (0x1F300 <= cp <= 0x1F9FF) or (0x1F600 <= cp <= 0x1F64F) or (0x1F000 <= cp <= 0x1F02F) or (0x1F680 <= cp <= 0x1F6FF):
                            unicode_emojis.append(f"U+{cp:05X} ({ch})")
                    if unicode_emojis:
                        emoji_entries = [(u, "•") for u in unicode_emojis]

            if not emoji_entries:
                await _send_safe(ctx.chat.id, "⚠️ Tin đó không có emoji/sticker để lấy ID. Thử reply tin có sticker hoặc tin có chữ kèm emoji (custom hoặc Unicode).", ctx.id)
                return

            # Tên sau lệnh: /getemoji Snow → ra dòng E_SNOW = '<emoji id="...">❄️</emoji>' để copy
            var_base = ""
            if len(ctx.command) > 1:
                var_base = _emoji_var_name(" ".join(ctx.command[1:]))
            ids_line = "\n".join(str(eid) for eid, _ in emoji_entries)
            if var_base:
                py_lines = []
                for i, (eid, fallback) in enumerate(emoji_entries):
                    var = f"{var_base}_{i + 1}" if len(emoji_entries) > 1 else var_base
                    if str(eid).isdigit():
                        fb_esc = (fallback or "•").replace("\\", "\\\\").replace("'", "\\'")
                        py_lines.append(f'{var} = \'<emoji id="{eid}">{fb_esc}</emoji>\'')
                    else:
                        py_lines.append(f"# {var}: {eid}")
                out = "\n".join(py_lines)
            else:
                out = f"Emoji ID (chạm để copy):\n\n{ids_line}"
            await _send_safe(ctx.chat.id, out, ctx.id)
        except Exception as e:
            LOGGER.warning("getid_emoji: %s", e)
            await _send_safe(ctx.chat.id, "⚠️ Lỗi khi lấy emoji ID. Thử reply tin có sticker hoặc tin có emoji trong nội dung.", ctx.id)
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
