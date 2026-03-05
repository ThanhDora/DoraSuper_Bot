# Bộ lọc (filters) - ưu tiên gửi emoji động (custom); lỗi thì fallback Unicode.
import asyncio
import re
import logging
from logging import getLogger

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.filters_db import (
    delete_filter,
    deleteall_filters,
    get_filter,
    get_filters_names,
    save_filter,
)
from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.core.decorator.permissions import adminsOnly, member_permissions
from dorasuper.core.keyboard import ikb
from dorasuper.helper.functions import extract_text_and_keyb, extract_urls
from dorasuper.vars import COMMAND_HANDLER
from dorasuper.emoji import E_NOTE, E_LIST, E_SUCCESS, E_CROSS, E_WARN, E_GROUP, E_TIP

LOGGER = getLogger("DoraSuper")


def _emoji_to_unicode(text: str) -> str:
    """Chuyển <emoji id="...">...</emoji> → Unicode (fallback khi custom emoji lỗi)."""
    return re.sub(r'<emoji id="[^"]+">(.+?)</emoji>', r'\1', str(text))


async def _reply_safe(message, text: str, **kwargs):
    """Gửi tin: thử emoji động (custom) trước, lỗi thì gửi bản Unicode."""
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    try:
        return await message.reply_text(text, **kwargs)
    except Exception:
        return await message.reply_text(_emoji_to_unicode(text), **kwargs)

__MODULE__ = "BộLọc"
__HELP__ = """
<blockquote>/xemboloc - Lấy tất cả các bộ lọc trong cuộc trò chuyện.
/boloc [TÊN_BỘ_LỌC] hoặc /themboloc [TÊN_BỘ_LỌC] - Lưu một bộ lọc (trả lời một tin nhắn).

Các loại bộ lọc được hỗ trợ là Văn bản, Hoạt hình, Ảnh, Tài liệu, Video, ghi chú video, Âm thanh, Giọng nói.

Để sử dụng nhiều từ trong một bộ lọc, hãy sử dụng
/boloc Hey_there hoặc /themboloc Hey_there để lọc "Hey there".
/xboloc [TÊN_BỘ_LỌC] hoặc /xoaboloc [TÊN_BỘ_LỌC] - Dừng một bộ lọc.
/xhboloc - Xóa tất cả các bộ lọc trong một cuộc trò chuyện (vĩnh viễn).</blockquote>
"""


async def _delete_after(msg, seconds: int):
    """Xóa tin nhắn sau vài giây (không chặn handler)."""
    if not msg:
        return
    try:
        await asyncio.sleep(seconds)
        await msg.delete()
    except Exception:
        pass


# group=-1: chạy trước các handler mặc định (group=0) để tránh plugin khác ảnh hưởng
# ---- Private: chỉ thông báo dùng trong nhóm ----
@app.on_message(
    filters.command(
        ["themboloc", "boloc", "xemboloc", "xboloc", "xoaboloc", "xhboloc"],
        COMMAND_HANDLER,
    )
    & filters.private,
    group=-1,
)
async def filters_private(_, message):
    await _reply_safe(
        message,
        f"{E_GROUP} <b>Bộ lọc chỉ dùng trong nhóm.</b>\nThêm bot vào nhóm rồi dùng lệnh ở đó.",
    )


# ---- Nhóm: thêm/sửa bộ lọc (admin) ----
@app.on_message(
    filters.command(["themboloc", "boloc"], COMMAND_HANDLER) & ~filters.private,
    group=-1,
)
@adminsOnly("can_change_info")
async def save_filters(_, message):
    try:
        if len(message.command) < 2 or not message.reply_to_message:
            await _reply_safe(
                message,
                f"{E_TIP} <b>Sử dụng:</b>\nTrả lời tin nhắn bằng <code>/boloc [Tên bộ lọc]</code> để thiết lập bộ lọc mới.",
            )
            return
        name = (message.text or "").split(None, 1)[1].strip()
        if not name:
            await _reply_safe(
                message,
                f"{E_WARN} <b>Sử dụng:</b> <code>/boloc [TÊN_BỘ_LỌC]</code>",
            )
            return
        chat_id = message.chat.id
        replied_message = message.reply_to_message
        text = name.split(" ", 1)
        if len(text) > 1:
            name = text[0]
            data = text[1].strip()
            if replied_message.sticker or replied_message.video_note:
                data = None
        elif replied_message.sticker or replied_message.video_note:
            data = None
        elif not replied_message.text and not replied_message.caption:
            data = None
        else:
            raw = replied_message.text or replied_message.caption or ""
            data = getattr(raw, "markdown", raw) if raw else None
        _type = "text"
        file_id = None
        if replied_message.sticker:
            _type = "sticker"
            file_id = replied_message.sticker.file_id
        if replied_message.animation:
            _type = "animation"
            file_id = replied_message.animation.file_id
        if replied_message.photo:
            _type = "photo"
            file_id = replied_message.photo.file_id
        if replied_message.document:
            _type = "document"
            file_id = replied_message.document.file_id
        if replied_message.video:
            _type = "video"
            file_id = replied_message.video.file_id
        if replied_message.video_note:
            _type = "video_note"
            file_id = replied_message.video_note.file_id
        if replied_message.audio:
            _type = "audio"
            file_id = replied_message.audio.file_id
        if replied_message.voice:
            _type = "voice"
            file_id = replied_message.voice.file_id
        if data and replied_message.reply_markup and not re.findall(
            r"\[.+\,.+\]", data
        ):
            if urls := extract_urls(replied_message.reply_markup):
                response = "\n".join(
                    [f"{name}=[{text}, {url}]" for name, text, url in urls]
                )
                data = data + response
        name = name.replace("_", " ")
        _filter = {"type": _type, "data": data, "file_id": file_id}
        await save_filter(chat_id, name, _filter)
        sent = await _reply_safe(
            message,
            f"{E_SUCCESS} <b>Đã lưu bộ lọc</b> <code>{name}</code>.",
        )
        asyncio.create_task(_delete_after(sent, 5))
    except UnboundLocalError:
        await _reply_safe(
            message,
            f"{E_WARN} Tin nhắn đã trả lời không thể truy cập. Chuyển tiếp tin nhắn và thử lại.",
        )
    except Exception as e:
        LOGGER.exception("save_filters: %s", e)
        await _reply_safe(
            message,
            f"{E_CROSS} Có lỗi khi lưu bộ lọc. Thử reply đúng tin nhắn.",
        )


# ---- Nhóm: xem danh sách bộ lọc ----
@app.on_message(
    filters.command("xemboloc", COMMAND_HANDLER) & ~filters.private,
    group=-1,
)
@capture_err
async def get_filterss(_, m):
    _filters = await get_filters_names(m.chat.id)
    if not _filters:
        await _reply_safe(m, f"{E_NOTE} Không có bộ lọc nào trong cuộc trò chuyện này.")
        return
    _filters.sort()
    msg = f"{E_LIST} <b>Danh sách bộ lọc</b> – {m.chat.title} (<code>{m.chat.id}</code>)\n\n"
    for fname in _filters:
        msg += f"• <code>{fname}</code>\n"
    await _reply_safe(m, msg)


# ---- Nhóm: xóa một bộ lọc (admin) ----
@app.on_message(
    filters.command(["xboloc", "xoaboloc"], COMMAND_HANDLER) & ~filters.private,
    group=-1,
)
@adminsOnly("can_change_info")
async def del_filter(_, m):
    if len(m.command) < 2:
        await _reply_safe(m, f"{E_TIP} <b>Sử dụng:</b> <code>/xoaboloc [TÊN_BỘ_LỌC]</code>")
        return
    name = (m.text or "").split(None, 1)[1].strip()
    if not name:
        await _reply_safe(m, f"{E_TIP} <b>Sử dụng:</b> <code>/xoaboloc [TÊN_BỘ_LỌC]</code>")
        return
    chat_id = m.chat.id
    deleted = await delete_filter(chat_id, name)
    if deleted:
        sent = await _reply_safe(m, f"{E_SUCCESS} Đã xoá bộ lọc <code>{name}</code>.")
        if sent:
            asyncio.create_task(_delete_after(sent, 5))
    else:
        sent = await _reply_safe(m, f"{E_CROSS} Không tìm thấy bộ lọc này.")
        if sent:
            asyncio.create_task(_delete_after(sent, 5))


# ---- Nhóm: trigger bộ lọc (tin nhắn thường) ----
@app.on_message(
    filters.text
    & ~filters.private
    & ~filters.channel
    & ~filters.via_bot
    & ~filters.forwarded,
    group=103,
)
async def filters_re(_, message):
    try:
        from_user = message.from_user or message.sender_chat
    except AttributeError:
        return
    if not from_user:
        return
    text = (message.text or "").lower().strip()
    if not text:
        return
    if message.command and message.command[0].lower() in ["boloc", "themboloc"]:
        return
    chat_id = message.chat.id
    list_of_filters = await get_filters_names(chat_id)
    for word in list_of_filters:
        pattern = r"( |^|[^\w])" + re.escape(word) + r"( |$|[^\w])"
        if not re.search(pattern, text, flags=re.IGNORECASE):
            continue
        _filter = await get_filter(chat_id, word)
        if _filter is False:
            continue
        data_type = _filter["type"]
        data = _filter.get("data")
        file_id = _filter.get("file_id")
        keyb = None
        if data is not None:
            if "{chat}" in data:
                data = data.replace("{chat}", message.chat.title or "")
            if "{name}" in data:
                name_val = from_user.mention if message.from_user else getattr(from_user, "title", "")
                data = data.replace("{name}", name_val or "")
            if data and re.findall(r"\[.+\,.+\]", data):
                keyboard = extract_text_and_keyb(ikb, data)
                if keyboard:
                    data, keyb = keyboard
        target = message
        if message.reply_to_message:
            replied_user = (
                message.reply_to_message.from_user
                or message.reply_to_message.sender_chat
            )
            if text.startswith("~"):
                try:
                    await message.delete()
                except Exception:
                    pass
            if replied_user and replied_user.id != from_user.id:
                target = message.reply_to_message
        if data_type == "text":
            await target.reply_text(
                text=(data or ""),
                reply_markup=keyb,
                disable_web_page_preview=True,
            )
            return
        if not file_id:
            continue
        try:
            if data_type == "sticker":
                await target.reply_sticker(sticker=file_id)
            elif data_type == "animation":
                await target.reply_animation(
                    animation=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            elif data_type == "photo":
                await target.reply_photo(
                    photo=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            elif data_type == "document":
                await target.reply_document(
                    document=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            elif data_type == "video":
                await target.reply_video(
                    video=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            elif data_type == "video_note":
                await target.reply_video_note(video_note=file_id)
            elif data_type == "audio":
                await target.reply_audio(
                    audio=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            elif data_type == "voice":
                await target.reply_voice(
                    voice=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
        except Exception as e:
            LOGGER.warning("filters_re send failed: %s", e)
        return


# ---- Nhóm: xóa tất cả bộ lọc (admin) ----
@app.on_message(
    filters.command("xhboloc", COMMAND_HANDLER) & ~filters.private,
    group=-1,
)
@adminsOnly("can_change_info")
async def stop_all(_, message):
    _filters = await get_filters_names(message.chat.id)
    if not _filters:
        await _reply_safe(message, f"{E_NOTE} Không có bộ lọc trong cuộc trò chuyện này.")
        return
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("OK, LÀM ĐI", callback_data="xboloc_yes"),
                InlineKeyboardButton("Huỷ", callback_data="xboloc_no"),
            ]
        ]
    )
    await _reply_safe(
        message,
        f"{E_WARN} <b>Xóa tất cả bộ lọc?</b>\nHành động này không thể hoàn tác.",
        reply_markup=keyboard,
    )


# ---- Callback: xác nhận xóa tất cả ----
@app.on_callback_query(filters.regex("xboloc_(.*)"))
async def stop_all_cb(_, cb):
    chat_id = cb.message.chat.id
    from_user = cb.from_user
    permissions = await member_permissions(chat_id, from_user.id)
    if "can_change_info" not in permissions:
        await cb.answer(
            "Bạn không có quyền cần thiết để thực hiện lệnh này.\nQuyền cần thiết: can_change_info",
            show_alert=True,
        )
        return
    inp = cb.data.split("_", 1)[1]
    await cb.answer()
    if inp == "yes":
        result = await deleteall_filters(chat_id)
        if result and result.deleted_count:
            try:
                await cb.message.edit_text(
                    f"{E_SUCCESS} Đã xóa thành công tất cả bộ lọc trong cuộc trò chuyện này.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                await cb.message.edit_text(
                    _emoji_to_unicode(f"{E_SUCCESS} Đã xóa thành công tất cả bộ lọc trong cuộc trò chuyện này."),
                )
        else:
            try:
                await cb.message.edit_text(
                    f"{E_NOTE} Không có bộ lọc nào để xóa.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                await cb.message.edit_text(
                    _emoji_to_unicode(f"{E_NOTE} Không có bộ lọc nào để xóa."),
                )
    elif inp == "no":
        try:
            if cb.message.reply_to_message:
                await cb.message.reply_to_message.delete()
        except Exception:
            pass
        try:
            await cb.message.delete()
        except Exception:
            pass
