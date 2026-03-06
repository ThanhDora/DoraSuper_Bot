import asyncio
import html
import io
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pilmoji import Pilmoji
from pyrogram import enums, filters
from pyrogram.errors.exceptions.bad_request_400 import BadRequest, DocumentInvalid
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, MessageEntity
from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.emoji import E_BELL, E_CHECK, E_GREEN, E_ID, E_ONE, E_PIN_LOC, E_RECYCLE, E_SPARKLE, E_STAT, E_THREE, E_TROPHY, E_TWO, E_USER, E_WAIT, E_LOADING
from dorasuper.vars import COMMAND_HANDLER
from database.checkin_db import (
    can_use_command, update_user_command_usage, is_checkin_enabled,
    set_checkin_enabled, get_checkin_start_date, log_checkin,
    get_user_total, get_top10, reset_checkin, get_last_checkin
)

def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _strip_custom_emoji_entities(entities):
    if not entities:
        return []
    return [
        e for e in entities
        if getattr(e, "type", None) != enums.MessageEntityType.CUSTOM_EMOJI
    ]


def _html_drop_custom_emoji(html_text: str) -> str:
    """Thay thẻ <emoji id="...">...</emoji> bằng ký tự bên trong để tránh DocumentInvalid (bot không dùng custom emoji trong checkin)."""
    if not html_text or "<emoji" not in html_text:
        return html_text
    return re.sub(
        r'<emoji\s+id="\d+"[^>]*>([^<]*)</emoji>',
        lambda m: (m.group(1).strip() or "•"),
        html_text,
        flags=re.IGNORECASE,
    )


def _html_to_entities(html_text: str):
    """Parse HTML subset + custom emoji to (text, entities)."""
    entities = []
    out = []
    out_len = 0  # UTF-16 length
    stack = []

    i = 0
    while i < len(html_text):
        if html_text[i] == "<":
            # Custom emoji: <emoji id="...">x</emoji>
            if html_text.startswith("<emoji", i):
                m = re.match(r'<emoji\s+id="(\d+)">', html_text[i:], re.IGNORECASE)
                if m:
                    emoji_id = m.group(1)
                    inner_start = i + m.end()
                    inner_end = html_text.find("</emoji>", inner_start)
                    if inner_end != -1:
                        inner = html.unescape(html_text[inner_start:inner_end])
                        fallback = (inner.strip() or "•")
                        out.append(fallback)
                        offset = out_len
                        length = _utf16_len(fallback)
                        out_len += length
                        entities.append(
                            MessageEntity(
                                type=enums.MessageEntityType.CUSTOM_EMOJI,
                                offset=offset,
                                length=length,
                                custom_emoji_id=int(emoji_id),
                            )
                        )
                        i = inner_end + len("</emoji>")
                        continue

            # Links: <a href="...">text</a>
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

            # Basic tags: <b>, <i>, <code>
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
                                MessageEntity(
                                    type=ent_type,
                                    offset=start,
                                    length=length,
                                )
                            )
                i += m.end()
                continue

            # Unknown tag → treat "<" as literal
            out.append("<")
            out_len += _utf16_len("<")
            i += 1
            continue

        next_lt = html_text.find("<", i)
        if next_lt == -1:
            chunk = html_text[i:]
            i = len(html_text)
        else:
            chunk = html_text[i:next_lt]
            i = next_lt
        if chunk:
            chunk = html.unescape(chunk)
            out.append(chunk)
            out_len += _utf16_len(chunk)

    return "".join(out), entities


async def _reply_html(msg: Message, html_text: str, **kwargs):
    text, entities = _html_to_entities(html_text)
    try:
        return await msg.reply_text(text, entities=entities, **kwargs)
    except DocumentInvalid:
        return await msg.reply_text(text, entities=_strip_custom_emoji_entities(entities), **kwargs)


async def _reply_photo_html(msg: Message, photo, html_caption: str, **kwargs):
    text, entities = _html_to_entities(html_caption)
    try:
        return await msg.reply_photo(photo, caption=text, caption_entities=entities, **kwargs)
    except DocumentInvalid:
        return await msg.reply_photo(photo, caption=text, caption_entities=_strip_custom_emoji_entities(entities), **kwargs)


async def _send_photo_html(chat_id, photo, html_caption: str, **kwargs):
    text, entities = _html_to_entities(html_caption)
    try:
        return await app.send_photo(chat_id, photo, caption=text, caption_entities=entities, **kwargs)
    except DocumentInvalid:
        return await app.send_photo(chat_id, photo, caption=text, caption_entities=_strip_custom_emoji_entities(entities), **kwargs)


async def _edit_caption_html(msg: Message, html_caption: str, **kwargs):
    text, entities = _html_to_entities(html_caption)
    try:
        return await msg.edit_caption(caption=text, caption_entities=entities, **kwargs)
    except (DocumentInvalid, BadRequest):
        try:
            return await msg.edit_caption(
                caption=text,
                caption_entities=_strip_custom_emoji_entities(entities),
                **kwargs,
            )
        except Exception:
            try:
                return await msg.edit_caption(caption=text, **kwargs)
            except Exception:
                safe_caption = _html_drop_custom_emoji(html_caption)
                st, ent = _html_to_entities(safe_caption)
                return await msg.edit_caption(caption=st, caption_entities=ent, **kwargs)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DEFAULT_PIC = "assets/profilepic.png"

async def _delete_after(msg: Message, seconds: int = 60):
    try:
        await asyncio.sleep(seconds)
        await msg.delete()
    except: pass

def _schedule_delete(msg: Message, seconds: int = 60):
    asyncio.create_task(_delete_after(msg, seconds))

def _display_name(user) -> str:
    name = (user.first_name or "").strip()
    if getattr(user, "last_name", None): name = (name + " " + user.last_name).strip()
    return name or f"User {user.id}"

def _mention_html(user_id: int, name: str) -> str:
    safe = html.escape(str(name))
    return f'<a href="tg://user?id={user_id}">{safe}</a>'

def _fmt_vn(dt_naive: datetime) -> str:
    if not dt_naive: return "Chưa ghi nhận"
    return dt_naive.replace(tzinfo=ZoneInfo("UTC")).astimezone(VN_TZ).strftime("%H:%M - %d/%m/%Y")

def _checkin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Điểm danh ngay", callback_data="checkin_do")],
        [
            InlineKeyboardButton("BXH Tháng", callback_data="checkin_rank_month"),
            InlineKeyboardButton("BXH Năm", callback_data="checkin_rank_year")
        ]
    ])

async def _get_avatar(user_id):
    try:
        photos = [p async for p in app.get_chat_photos(user_id, limit=1)]
        if photos:
            path = await app.download_media(photos[0].file_id)
            img = Image.open(path).convert("RGBA")
            os.remove(path)
            return img
    except: pass
    if os.path.exists(DEFAULT_PIC): return Image.open(DEFAULT_PIC).convert("RGBA")
    return Image.new("RGBA", (200, 200), (40, 44, 52, 255))

def _make_card(name, uid, total, last_time, avatar_img, group_name):
    card = Image.new("RGBA", (800, 450), (15, 15, 25, 255))
    draw = ImageDraw.Draw(card)
    # Gradient: vẽ từng block 5px thay vì 450 line → nhanh hơn
    for i in range(0, 450, 5):
        y2 = min(i + 5, 450)
        fill = (20, int(30 + (i / 450) * 40), int(50 + (i / 450) * 60), 255)
        draw.rectangle([0, i, 800, y2], fill=fill)
    draw.rounded_rectangle([20, 20, 780, 430], radius=30, outline=(0, 255, 204, 100), width=3)
    avatar = avatar_img.resize((180, 180))
    mask = Image.new("L", (180, 180), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 180, 180), fill=255)
    avatar.putalpha(mask)
    card.paste(avatar, (50, 130), avatar)
    try:
        f_bold = ImageFont.truetype("assets/Roboto-Bold.ttf", 42)
        f_reg = ImageFont.truetype("assets/Roboto-Regular.ttf", 26)
        f_sub = ImageFont.truetype("assets/Roboto-Regular.ttf", 22)
    except:
        f_bold = ImageFont.load_default(); f_reg = ImageFont.load_default(); f_sub = ImageFont.load_default()
    try:
        with Pilmoji(card) as pilmoji:
            pilmoji.text((50, 50), "CHỨNG NHẬN ĐIỂM DANH ✅", fill="#00FFCC", font=f_bold)
            pilmoji.text((260, 140), f"👤 Thành viên: {name}", fill="white", font=f_reg)
            pilmoji.text((260, 190), f"🆔 ID: {uid}", fill="#BBBBBB", font=f_reg)
            pilmoji.text((260, 240), f"🏆 Tích lũy: {total} lượt", fill="#FFD700", font=f_reg)
            pilmoji.text((260, 290), f"🕒 Lần cuối: {last_time}", fill="#00BFFF", font=f_reg)
            pilmoji.text((50, 385), f"📍 Nhóm: {group_name}", fill="#888888", font=f_sub)
    except Exception:
        draw.text((50, 50), "CHUNG NHAN DIEM DANH", fill="#00FFCC", font=f_bold)
        draw.text((260, 140), f"Thanh vien: {name}", fill="white", font=f_reg)
        draw.text((260, 190), f"ID: {uid}", fill="#BBBBBB", font=f_reg)
        draw.text((260, 240), f"Tich luy: {total} luot", fill="#FFD700", font=f_reg)
        draw.text((260, 290), f"Lan cuoi: {last_time}", fill="#00BFFF", font=f_reg)
        draw.text((50, 385), f"Nhom: {group_name}", fill="#888888", font=f_sub)
    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="JPEG", quality=95)
    buf.seek(0)
    buf.name = "checkin.jpg"
    return buf

@app.on_message(filters.command("checkin", COMMAND_HANDLER), group=-1)
@capture_err
async def checkin_cmd(_, ctx: Message):
    if not ctx.chat or not await is_checkin_enabled(ctx.chat.id): return
    target = ctx.reply_to_message.from_user if (ctx.reply_to_message and ctx.reply_to_message.from_user) else ctx.from_user

    wait_text = f"{E_LOADING} <b>Đang xử lý dữ liệu...</b>"
    wait_msg = await _reply_html(ctx, wait_text, quote=True)

    # Chạy song song: DB + tải avatar (tránh chờ tuần tự)
    total, last_ts, avatar, can_use = await asyncio.gather(
        get_user_total(ctx.chat.id, target.id),
        get_last_checkin(ctx.chat.id, target.id),
        _get_avatar(target.id),
        can_use_command(ctx.chat.id, target.id, "checkin"),
    )
    # Tạo ảnh trong thread để không block event loop (PIL/Pilmoji tốn CPU)
    loop = asyncio.get_event_loop()
    card = await loop.run_in_executor(
        None,
        lambda: _make_card(_display_name(target), target.id, total, _fmt_vn(last_ts), avatar, ctx.chat.title),
    )

    status = f"{E_GREEN} Chờ điểm danh" if can_use else f"{E_CHECK} Đã xong hôm nay"
    chat_title = html.escape(str(ctx.chat.title or "Chat"))
    caption = f"{E_USER} Thành viên: {_mention_html(target.id, _display_name(target))}\n{E_ID} ID: <code>{target.id}</code>\n{E_PIN_LOC} Tại: <b>{chat_title}</b>\n{E_STAT} Trạng thái: {status}"

    await wait_msg.delete()
    m = await _reply_photo_html(
        ctx,
        card,
        caption,
        reply_markup=_checkin_keyboard() if target.id == ctx.from_user.id else None,
    )
    _schedule_delete(m)

@app.on_callback_query(filters.regex("^checkin_do$"))
async def checkin_do_cb(_, cb: CallbackQuery):
    if not await can_use_command(cb.message.chat.id, cb.from_user.id, "checkin"):
        return await cb.answer("Bạn đã hoàn thành điểm danh hôm nay!", show_alert=True)

    await cb.answer("⏳ Đang ghi nhận điểm danh...", show_alert=False)

    ts = await log_checkin(cb.message.chat.id, cb.from_user.id, _display_name(cb.from_user))
    await update_user_command_usage(cb.message.chat.id, cb.from_user.id, "checkin")

    # Song song: lấy total + avatar, sau đó tạo ảnh trong thread
    total, avatar = await asyncio.gather(
        get_user_total(cb.message.chat.id, cb.from_user.id),
        _get_avatar(cb.from_user.id),
    )
    loop = asyncio.get_event_loop()
    card = await loop.run_in_executor(
        None,
        lambda: _make_card(_display_name(cb.from_user), cb.from_user.id, total, _fmt_vn(ts), avatar, cb.message.chat.title),
    )

    await cb.message.delete()
    chat_title = html.escape(str(cb.message.chat.title or "Chat"))
    caption = f"{E_SPARKLE} <b>Điểm danh thành công!</b>\n{E_USER} Chào: {_mention_html(cb.from_user.id, _display_name(cb.from_user))}\n{E_PIN_LOC} Nhóm: <b>{chat_title}</b>"
    m = await _send_photo_html(
        cb.message.chat.id,
        card,
        caption,
        reply_markup=_checkin_keyboard(),
    )
    _schedule_delete(m)

@app.on_callback_query(filters.regex("^checkin_rank_(month|year)$"))
async def rank_cb(_, cb: CallbackQuery):
    is_m = "month" in cb.data; now = datetime.now(VN_TZ)
    top = await get_top10(cb.message.chat.id, year=now.year, month=now.month if is_m else None)
    chat_title = html.escape(str(cb.message.chat.title or "Chat"))
    res = f"{E_TROPHY} <b>BẢNG VÀNG {'THÁNG ' + str(now.month) if is_m else 'NĂM ' + str(now.year)}</b>\n{E_PIN_LOC} Nhóm: <b>{chat_title}</b>\n\n"
    if not top:
        res += "<i>Chưa có dữ liệu</i>"
    else:
        for i, it in enumerate(top, 1):
            medal = E_ONE if i == 1 else E_TWO if i == 2 else E_THREE if i == 3 else f"{i}."
            res += f"{medal} {_mention_html(it['_id'], it.get('user_name') or 'User')} — <code>{it['count']}</code> lượt\n"
    await _edit_caption_html(cb.message, res, reply_markup=_checkin_keyboard())

@app.on_message(filters.command("checkin_rank", COMMAND_HANDLER), group=-1)
@capture_err
async def rank_cmd(_, ctx: Message):
    now = datetime.now(VN_TZ)
    top = await get_top10(ctx.chat.id, year=now.year, month=now.month)
    chat_title = html.escape(str(ctx.chat.title or "Chat"))
    res = f"{E_STAT} <b>TOP 10 ĐIỂM DANH THÁNG {now.month}</b>\n{E_PIN_LOC} Tại: <b>{chat_title}</b>\n\n"
    if top:
        for i, it in enumerate(top, 1):
            medal = E_ONE if i == 1 else E_TWO if i == 2 else E_THREE if i == 3 else f"{i}."
            res += f"{medal} {_mention_html(it['_id'], it.get('user_name') or 'User')} — <code>{it['count']}</code> lượt\n"
    else:
        res = res.rstrip() + "\n<i>Chưa có dữ liệu</i>"
    reply_text = res or "Chưa có dữ liệu."
    m = await _reply_html(ctx, reply_text, reply_markup=_checkin_keyboard())
    _schedule_delete(m)

@app.on_cmd(["checkin_set", "checkin_reset"], self_admin=True, group_only=True, group=-1)
@app.adminsOnly("can_change_info")
async def admin_ctrl(_, ctx: Message):
    cmd = (ctx.command or [""])[0].lower()
    if cmd == "checkin_reset":
        await reset_checkin(ctx.chat.id)
        chat_title = html.escape(str(ctx.chat.title or "Chat"))
        txt = f"{E_RECYCLE} Đã làm mới bảng điểm của nhóm <b>{chat_title}</b>."
        await _reply_html(ctx, txt)
    else:
        val = "on" in (ctx.text or "").lower()
        await set_checkin_enabled(ctx.chat.id, val)
        chat_title = html.escape(str(ctx.chat.title or "Chat"))
        txt = f"{E_BELL} Đã {'Bật' if val else 'Tắt'} điểm danh tại <b>{chat_title}</b>."
        await _reply_html(ctx, txt)