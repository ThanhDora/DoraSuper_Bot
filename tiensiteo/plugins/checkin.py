import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.vars import COMMAND_HANDLER

from database.checkin_db import (
    can_use_command,
    update_user_command_usage,
    is_checkin_enabled,
    set_checkin_enabled,
    get_checkin_start_date,
    log_checkin,
    get_user_total,
    get_top10,
    reset_checkin,
)

__MODULE__ = "Checkin"
__HELP__ = (
    "<blockquote>"
    "/checkin - Điểm danh + xem điểm (reply ai đó để xem điểm người đó)\n"
    "/checkin_rank - Xem BXH top 10 theo THÁNG và NĂM\n"
    "/checkin_set on|off - Bật/tắt điểm danh cho nhóm (admin)\n"
    "/checkin_reset - Reset bảng điểm danh của nhóm (admin)\n"
    "</blockquote>"
)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
AUTO_DEL_SEC = 30


# ----------------------------
# Auto delete helpers
# ----------------------------
async def _delete_after(msg: Message, seconds: int = AUTO_DEL_SEC):
    try:
        await asyncio.sleep(seconds)
        await msg.delete()
    except Exception:
        pass


def _schedule_delete(msg: Message, seconds: int = AUTO_DEL_SEC):
    try:
        asyncio.create_task(_delete_after(msg, seconds))
    except Exception:
        pass


async def _reply_autodel(message: Message, text: str, **kwargs) -> Message:
    m = await message.reply_text(text, **kwargs)
    _schedule_delete(m)
    return m


async def _replymsg_autodel(message: Message, text: str, **kwargs) -> Message:
    # project của bạn hay dùng reply_msg; nhưng không phải mọi Message đều có
    if hasattr(message, "reply_msg"):
        m = await message.reply_msg(text, **kwargs)
    else:
        m = await message.reply_text(text, **kwargs)
    _schedule_delete(m)
    return m


# ----------------------------
# UI helpers
# ----------------------------
def _checkin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Điểm danh", callback_data="checkin_do")],
            [
                InlineKeyboardButton("📊 BXH Tháng", callback_data="checkin_rank_month"),
                InlineKeyboardButton("🏆 BXH Năm", callback_data="checkin_rank_year"),
            ],
        ]
    )


def _display_name(user) -> str:
    name = (user.first_name or "").strip()
    if getattr(user, "last_name", None):
        name = (name + " " + user.last_name).strip()
    return name or f"User {user.id}"


def _mention_md(user_id: int, name: str) -> str:
    safe = name.replace("[", "(").replace("]", ")")
    return f"[{safe}](tg://user?id={user_id})"


def _now_vn_ym() -> tuple[int, int]:
    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    vn = now_utc.astimezone(VN_TZ)
    return vn.year, vn.month


def _fmt_dt_vn_from_utc_naive(dt_utc_naive: datetime) -> str:
    dt = dt_utc_naive.replace(tzinfo=ZoneInfo("UTC"))
    vn = dt.astimezone(VN_TZ)
    return vn.strftime("%H:%M:%S %d/%m/%Y")


def _fmt_start_date(dt_utc_naive: datetime) -> str:
    dt = dt_utc_naive.replace(tzinfo=ZoneInfo("UTC"))
    vn = dt.astimezone(VN_TZ)
    return vn.strftime("%d/%m/%Y")


def _rank_medal(i: int) -> str:
    if i == 1:
        return "🥇"
    if i == 2:
        return "🥈"
    if i == 3:
        return "🥉"
    return f"{i}."


async def _render_rank_text(chat_id: int) -> str:
    y, m = _now_vn_ym()
    start_date = await get_checkin_start_date(chat_id)

    top_month = await get_top10(chat_id, year=y, month=m)
    top_year = await get_top10(chat_id, year=y)

    def fmt(items):
        if not items:
            return "Chưa có ai điểm danh."
        lines = []
        for i, it in enumerate(items, start=1):
            uid = it.get("_id")
            name = it.get("user_name") or f"User {uid}"
            mention = _mention_md(uid, name)
            lines.append(f"{_rank_medal(i)} {mention} — **{it.get('count', 0)}**")
        return "\n".join(lines)

    return (
        f"🗓️ Tính từ: **{_fmt_start_date(start_date)}** (giờ VN)\n\n"
        f"📊 **Top 10 tháng {m:02d}/{y}**\n{fmt(top_month)}\n\n"
        f"🏆 **Top 10 năm {y}**\n{fmt(top_year)}"
    )


# ----------------------------
# Commands
# ----------------------------
@app.on_message(filters.command(["checkin"], COMMAND_HANDLER))
@capture_err
async def checkin_command(_, ctx: Message):
    if ctx.chat is None:
        await _reply_autodel(ctx, "Lệnh này chỉ dùng trong chat/group.", reply_to_message_id=ctx.id)
        return

    enabled = await is_checkin_enabled(ctx.chat.id)
    if not enabled:
        await _reply_autodel(ctx, "🚫 Điểm danh đang bị tắt trong nhóm này.", reply_to_message_id=ctx.id)
        return
    target = None
    if ctx.reply_to_message and ctx.reply_to_message.from_user:
        target = ctx.reply_to_message.from_user
    else:
        target = ctx.from_user

    if target is None:
        await _reply_autodel(ctx, "Không xác định được người cần kiểm tra.", reply_to_message_id=ctx.id)
        return

    y, mth = _now_vn_ym()
    name = _display_name(target)
    who = _mention_md(target.id, name)

    total_month = await get_user_total(ctx.chat.id, target.id, year=y, month=mth)
    total_year = await get_user_total(ctx.chat.id, target.id, year=y)
    total_all = await get_user_total(ctx.chat.id, target.id)
    if ctx.from_user and target.id == ctx.from_user.id:
        can = await can_use_command(ctx.chat.id, target.id, "checkin")
        status_line = "🟢 Hôm nay: **chưa điểm danh**" if can else "✅ Hôm nay: **đã điểm danh**"

        text = (
            f"👤 {who}\n"
            f"{status_line}\n\n"
            f"📌 Điểm:\n"
            f"• Tháng {mth:02d}/{y}: **{total_month}**\n"
            f"• Năm {y}: **{total_year}**\n"
            f"• Tổng: **{total_all}**"
        )
        m = await ctx.reply_text(
            text,
            reply_markup=_checkin_keyboard(),
            reply_to_message_id=ctx.id,
            disable_web_page_preview=True
        )
        _schedule_delete(m)
        return
    can = await can_use_command(ctx.chat.id, target.id, "checkin")
    status_line = "🟢 Hôm nay: **chưa điểm danh**" if can else "✅ Hôm nay: **đã điểm danh**"

    text = (
        f"👤 {who}\n"
        f"{status_line}\n\n"
        f"📌 Điểm:\n"
        f"• Tháng {mth:02d}/{y}: **{total_month}**\n"
        f"• Năm {y}: **{total_year}**\n"
        f"• Tổng: **{total_all}**"
    )
    await _reply_autodel(ctx, text, reply_to_message_id=ctx.id, disable_web_page_preview=True)


@app.on_message(filters.command(["checkin_rank"], COMMAND_HANDLER))
@capture_err
async def checkin_rank(_, ctx: Message):
    if ctx.chat is None:
        await _reply_autodel(ctx, "Lệnh này chỉ dùng trong chat/group.", reply_to_message_id=ctx.id)
        return

    text = await _render_rank_text(ctx.chat.id)
    await _reply_autodel(ctx, text, reply_to_message_id=ctx.id, disable_web_page_preview=True)


# ----------------------------
# Admin commands
# ----------------------------
@app.on_cmd(["checkin_set"], self_admin=True, group_only=True)
@app.adminsOnly("can_change_info")
@capture_err
async def checkin_set_cmd(client, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await _replymsg_autodel(message, "Dùng: `/checkin_set on` hoặc `/checkin_set off`")
        return

    arg = parts[1].strip().lower()
    if arg not in ("on", "off"):
        await _replymsg_autodel(message, "Dùng: `/checkin_set on` hoặc `/checkin_set off`")
        return

    enabled = arg == "on"
    await set_checkin_enabled(message.chat.id, enabled)

    if enabled:
        start_date = await get_checkin_start_date(message.chat.id)
        await _replymsg_autodel(
            message,
            f"✅ Đã **bật** điểm danh.\n🗓️ Tính từ: **{_fmt_start_date(start_date)}** (giờ VN)"
        )
    else:
        await _replymsg_autodel(message, "⛔ Đã **tắt** điểm danh cho nhóm này.")


@app.on_cmd(["checkin_reset"], self_admin=True, group_only=True)
@app.adminsOnly("can_change_info")
@capture_err
async def checkin_reset_cmd(client, message: Message):
    now = await reset_checkin(message.chat.id)
    await _replymsg_autodel(
        message,
        "♻️ Đã **reset** bảng điểm danh.\n"
        f"🗓️ Ngày bắt đầu mới: **{_fmt_start_date(now)}** (giờ VN)"
    )


# ----------------------------
# Callback handlers
# ----------------------------
@app.on_callback_query(filters.regex(r"^checkin_do$"))
async def checkin_do_callback(_, cb: CallbackQuery):
    try:
        chat = cb.message.chat if cb.message else None
        user = cb.from_user
        if chat is None or user is None:
            return await cb.answer("Không hợp lệ.", show_alert=True)

        enabled = await is_checkin_enabled(chat.id)
        if not enabled:
            return await cb.answer("Nhóm đang tắt điểm danh.", show_alert=True)

        ok = await can_use_command(chat.id, user.id, "checkin")
        y, mth = _now_vn_ym()

        name = _display_name(user)
        me = _mention_md(user.id, name)

        if not ok:
            total_month = await get_user_total(chat.id, user.id, year=y, month=mth)
            total_year = await get_user_total(chat.id, user.id, year=y)
            total_all = await get_user_total(chat.id, user.id)

            await cb.answer("Bạn đã điểm danh hôm nay rồi 😄", show_alert=True)
            if cb.message:
                text = (
                    f"👤 {me}\n"
                    f"✅ Hôm nay: **đã điểm danh**\n\n"
                    f"📌 Điểm:\n"
                    f"• Tháng {mth:02d}/{y}: **{total_month}**\n"
                    f"• Năm {y}: **{total_year}**\n"
                    f"• Tổng: **{total_all}**"
                )
                await cb.message.edit_text(text, reply_markup=_checkin_keyboard(), disable_web_page_preview=True)
                _schedule_delete(cb.message)
            return

        # log checkin
        ts = await log_checkin(chat.id, user.id, name)
        await update_user_command_usage(chat.id, user.id, "checkin")

        total_month = await get_user_total(chat.id, user.id, year=y, month=mth)
        total_year = await get_user_total(chat.id, user.id, year=y)
        total_all = await get_user_total(chat.id, user.id)

        await cb.answer("✅ Điểm danh thành công!", show_alert=False)

        if cb.message:
            text = (
                f"✅ **Điểm danh thành công!**\n"
                f"👤 {me}\n"
                f"🕒 { _fmt_dt_vn_from_utc_naive(ts) } (giờ VN)\n\n"
                f"📌 Điểm:\n"
                f"• Tháng {mth:02d}/{y}: **{total_month}**\n"
                f"• Năm {y}: **{total_year}**\n"
                f"• Tổng: **{total_all}**"
            )
            await cb.message.edit_text(text, reply_markup=_checkin_keyboard(), disable_web_page_preview=True)
            _schedule_delete(cb.message)

    except Exception as e:
        try:
            await cb.answer(f"Lỗi: {e}", show_alert=True)
        except Exception:
            pass


@app.on_callback_query(filters.regex(r"^checkin_rank_month$"))
async def checkin_rank_month_cb(_, cb: CallbackQuery):
    try:
        chat = cb.message.chat if cb.message else None
        if chat is None:
            return await cb.answer("Không hợp lệ.", show_alert=True)

        y, m = _now_vn_ym()
        start_date = await get_checkin_start_date(chat.id)
        top = await get_top10(chat.id, year=y, month=m)

        if not top:
            text = (
                f"📊 **Top 10 tháng {m:02d}/{y}**\n"
                f"🗓️ Tính từ: **{_fmt_start_date(start_date)}**\n\n"
                "Chưa có ai điểm danh."
            )
        else:
            lines = []
            for i, it in enumerate(top, start=1):
                uid = it.get("_id")
                nm = it.get("user_name") or f"User {uid}"
                mention = _mention_md(uid, nm)
                lines.append(f"{_rank_medal(i)} {mention} — **{it.get('count', 0)}**")

            text = (
                f"📊 **Top 10 tháng {m:02d}/{y}**\n"
                f"🗓️ Tính từ: **{_fmt_start_date(start_date)}**\n\n"
                + "\n".join(lines)
            )

        if cb.message:
            await cb.message.edit_text(text, reply_markup=_checkin_keyboard(), disable_web_page_preview=True)
            _schedule_delete(cb.message)
        await cb.answer("OK")

    except Exception as e:
        await cb.answer(f"Lỗi: {e}", show_alert=True)


@app.on_callback_query(filters.regex(r"^checkin_rank_year$"))
async def checkin_rank_year_cb(_, cb: CallbackQuery):
    try:
        chat = cb.message.chat if cb.message else None
        if chat is None:
            return await cb.answer("Không hợp lệ.", show_alert=True)

        y, _m = _now_vn_ym()
        start_date = await get_checkin_start_date(chat.id)
        top = await get_top10(chat.id, year=y)

        if not top:
            text = (
                f"🏆 **Top 10 năm {y}**\n"
                f"🗓️ Tính từ: **{_fmt_start_date(start_date)}**\n\n"
                "Chưa có ai điểm danh."
            )
        else:
            lines = []
            for i, it in enumerate(top, start=1):
                uid = it.get("_id")
                nm = it.get("user_name") or f"User {uid}"
                mention = _mention_md(uid, nm)
                lines.append(f"{_rank_medal(i)} {mention} — **{it.get('count', 0)}**")

            text = (
                f"🏆 **Top 10 năm {y}**\n"
                f"🗓️ Tính từ: **{_fmt_start_date(start_date)}**\n\n"
                + "\n".join(lines)
            )

        if cb.message:
            await cb.message.edit_text(text, reply_markup=_checkin_keyboard(), disable_web_page_preview=True)
            _schedule_delete(cb.message)
        await cb.answer("OK")

    except Exception as e:
        await cb.answer(f"Lỗi: {e}", show_alert=True)
