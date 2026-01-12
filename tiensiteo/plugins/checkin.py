import asyncio, io, os
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pilmoji import Pilmoji
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.vars import COMMAND_HANDLER
from database.checkin_db import (
    can_use_command, update_user_command_usage, is_checkin_enabled, 
    set_checkin_enabled, get_checkin_start_date, log_checkin, 
    get_user_total, get_top10, reset_checkin, get_last_checkin
)

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

def _mention_md(user_id: int, name: str) -> str:
    return f"[{name.replace('[', '(').replace(']', ')') }](tg://user?id={user_id})"

def _fmt_vn(dt_naive: datetime) -> str:
    if not dt_naive: return "Chưa ghi nhận"
    return dt_naive.replace(tzinfo=ZoneInfo("UTC")).astimezone(VN_TZ).strftime("%H:%M - %d/%m/%Y")

def _checkin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Điểm danh ngay", callback_data="checkin_do")],
        [
            InlineKeyboardButton("📊 BXH Tháng", callback_data="checkin_rank_month"),
            InlineKeyboardButton("🏆 BXH Năm", callback_data="checkin_rank_year")
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
    for i in range(450):
        draw.line([(0, i), (800, i)], fill=(20, int(30 + (i/450)*40), int(50 + (i/450)*60), 255))
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
    with Pilmoji(card) as pilmoji:
        pilmoji.text((50, 50), "CHỨNG NHẬN ĐIỂM DANH ✅", fill="#00FFCC", font=f_bold)
        pilmoji.text((260, 140), f"👤 Thành viên: {name}", fill="white", font=f_reg)
        pilmoji.text((260, 190), f"🆔 ID: {uid}", fill="#BBBBBB", font=f_reg)
        pilmoji.text((260, 240), f"🏆 Tích lũy: {total} lượt", fill="#FFD700", font=f_reg)
        pilmoji.text((260, 290), f"🕒 Lần cuối: {last_time}", fill="#00BFFF", font=f_reg)
        pilmoji.text((50, 385), f"📍 Nhóm: {group_name}", fill="#888888", font=f_sub)
    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf

@app.on_message(filters.command("checkin", COMMAND_HANDLER))
@capture_err
async def checkin_cmd(_, ctx: Message):
    if not ctx.chat or not await is_checkin_enabled(ctx.chat.id): return
    target = ctx.reply_to_message.from_user if (ctx.reply_to_message and ctx.reply_to_message.from_user) else ctx.from_user
    
    wait_msg = await ctx.reply("⏳ **Đang xử lý dữ liệu...**", quote=True)
    
    total = await get_user_total(ctx.chat.id, target.id)
    last_ts = await get_last_checkin(ctx.chat.id, target.id)
    avatar = await _get_avatar(target.id)
    card = _make_card(_display_name(target), target.id, total, _fmt_vn(last_ts), avatar, ctx.chat.title)
    
    status = "🟢 Chờ điểm danh" if await can_use_command(ctx.chat.id, target.id, "checkin") else "✅ Đã xong hôm nay"
    caption = f"👤 Thành viên: {_mention_md(target.id, _display_name(target))}\n📍 Tại: **{ctx.chat.title}**\n📊 Trạng thái: {status}"
    
    await wait_msg.delete()
    m = await ctx.reply_photo(card, caption=caption, reply_markup=_checkin_keyboard() if target.id == ctx.from_user.id else None)
    _schedule_delete(m)

@app.on_callback_query(filters.regex("^checkin_do$"))
async def checkin_do_cb(_, cb: CallbackQuery):
    if not await can_use_command(cb.message.chat.id, cb.from_user.id, "checkin"):
        return await cb.answer("Bạn đã hoàn thành điểm danh hôm nay!", show_alert=True)
    
    await cb.answer("⏳ Đang ghi nhận điểm danh...", show_alert=False)
    
    ts = await log_checkin(cb.message.chat.id, cb.from_user.id, _display_name(cb.from_user))
    await update_user_command_usage(cb.message.chat.id, cb.from_user.id, "checkin")
    total = await get_user_total(cb.message.chat.id, cb.from_user.id)
    avatar = await _get_avatar(cb.from_user.id)
    card = _make_card(_display_name(cb.from_user), cb.from_user.id, total, _fmt_vn(ts), avatar, cb.message.chat.title)
    
    await cb.message.delete()
    caption = f"✨ **Điểm danh thành công!**\n👤 Chào: {_mention_md(cb.from_user.id, _display_name(cb.from_user))}\n📍 Nhóm: **{cb.message.chat.title}**"
    m = await app.send_photo(cb.message.chat.id, card, caption=caption, reply_markup=_checkin_keyboard())
    _schedule_delete(m)

@app.on_callback_query(filters.regex("^checkin_rank_(month|year)$"))
async def rank_cb(_, cb: CallbackQuery):
    is_m = "month" in cb.data; now = datetime.now(VN_TZ)
    top = await get_top10(cb.message.chat.id, year=now.year, month=now.month if is_m else None)
    res = f"🏆 **BẢNG VÀNG {'THÁNG ' + str(now.month) if is_m else 'NĂM ' + str(now.year)}**\n📍 Nhóm: **{cb.message.chat.title}**\n\n"
    if not top: res += "_Chưa có dữ liệu_"
    for i, it in enumerate(top, 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        res += f"{medal} {_mention_md(it['_id'], it.get('user_name', 'User'))} — `{it['count']}` lượt\n"
    await cb.message.edit_caption(caption=res, reply_markup=_checkin_keyboard())

@app.on_message(filters.command("checkin_rank", COMMAND_HANDLER))
@capture_err
async def rank_cmd(_, ctx: Message):
    now = datetime.now(VN_TZ); top = await get_top10(ctx.chat.id, year=now.year, month=now.month)
    res = f"📊 **TOP 10 ĐIỂM DANH THÁNG {now.month}**\n📍 Tại: **{ctx.chat.title}**\n\n"
    for i, it in enumerate(top, 1):
        res += f"{i}. {_mention_md(it['_id'], it.get('user_name'))} — `{it['count']}` lượt\n"
    m = await ctx.reply(res or "Chưa có dữ liệu.", reply_markup=_checkin_keyboard())
    _schedule_delete(m)

@app.on_cmd(["checkin_set", "checkin_reset"], self_admin=True, group_only=True)
@app.adminsOnly("can_change_info")
async def admin_ctrl(_, ctx: Message):
    if "set" in ctx.text.lower():
        val = "on" in ctx.text.lower()
        await set_checkin_enabled(ctx.chat.id, val)
        await ctx.reply(f"🔔 Đã {'Bật' if val else 'Tắt'} điểm danh tại **{ctx.chat.title}**.")
    else:
        await reset_checkin(ctx.chat.id)
        await ctx.reply(f"♻️ Đã làm mới bảng điểm của nhóm **{ctx.chat.title}**.")