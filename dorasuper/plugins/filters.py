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


async def _reply_filter(message, text: str, **kwargs):
    """Gửi phản hồi (có emoji → dùng HTML)."""
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    try:
        return await message.reply_msg(text, **kwargs)
    except (AttributeError, TypeError):
        return await message.reply_text(text, **kwargs)

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


@app.on_message(
    filters.command(["themboloc", "boloc", "xemboloc", "xboloc", "xoaboloc", "xhboloc"], COMMAND_HANDLER) & filters.private
)
async def filters_private(_, message):
    await _reply_filter(message, f"{E_GROUP} <b>Bộ lọc chỉ dùng trong nhóm.</b>\nThêm bot vào nhóm rồi dùng lệnh ở đó.")


@app.on_message(
    filters.command(["themboloc", "boloc"], COMMAND_HANDLER) & ~filters.private
)
@adminsOnly("can_change_info")
async def save_filters(_, message):
    try:
        if len(message.command) < 2 or not message.reply_to_message:
            return await _reply_filter(
                message,
                f"{E_TIP} <b>Sử dụng:</b>\nTrả lời tin nhắn bằng <code>/boloc [Tên bộ lọc]</code> để thiết lập bộ lọc mới.",
            )
        name = (message.text or "").split(None, 1)[1].strip()
        if not name:
            return await _reply_filter(message, f"{E_WARN} <b>Sử dụng:</b> <code>/boloc [TÊN_BỘ_LỌC]</code>")
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
        if data and replied_message.reply_markup and not re.findall(r"\[.+\,.+\]", data):
            if urls := extract_urls(replied_message.reply_markup):
                response = "\n".join(
                    [f"{name}=[{text}, {url}]" for name, text, url in urls]
                )
                data = data + response
        name = name.replace("_", " ")
        _filter = {
            "type": _type,
            "data": data,
            "file_id": file_id,
        }
        await save_filter(chat_id, name, _filter)
        return await _reply_filter(message, f"{E_SUCCESS} <b>Đã lưu bộ lọc</b> <code>{name}</code>.", del_in=5)
    except UnboundLocalError:
        return await _reply_filter(
            message,
            f"{E_WARN} Tin nhắn đã trả lời không thể truy cập. Chuyển tiếp tin nhắn và thử lại.",
        )
    except Exception as e:
        LOGGER.exception("save_filters: %s", e)
        return await _reply_filter(message, f"{E_CROSS} Có lỗi khi lưu bộ lọc. Thử reply đúng tin nhắn.")


@app.on_message(filters.command("xemboloc", COMMAND_HANDLER) & ~filters.private)
@capture_err
async def get_filterss(_, m):
    _filters = await get_filters_names(m.chat.id)
    if not _filters:
        return await _reply_filter(m, f"{E_NOTE} Không có bộ lọc nào trong cuộc trò chuyện này.")
    _filters.sort()
    msg = f"{E_LIST} <b>Danh sách bộ lọc</b> – {m.chat.title} (<code>{m.chat.id}</code>)\n\n"
    for fname in _filters:
        msg += f"• <code>{fname}</code>\n"
    await _reply_filter(m, msg)


@app.on_message(
    filters.command(["xboloc", "xoaboloc"], COMMAND_HANDLER) & ~filters.private
)
@adminsOnly("can_change_info")
async def del_filter(_, m):
    if len(m.command) < 2:
        return await _reply_filter(m, f"{E_TIP} <b>Sử dụng:</b> <code>/xoaboloc [TÊN_BỘ_LỌC]</code>")
    name = (m.text or "").split(None, 1)[1].strip()
    if not name:
        return await _reply_filter(m, f"{E_TIP} <b>Sử dụng:</b> <code>/xoaboloc [TÊN_BỘ_LỌC]</code>")
    chat_id = m.chat.id
    deleted = await delete_filter(chat_id, name)
    if deleted:
        return await _reply_filter(m, f"{E_SUCCESS} Đã xoá bộ lọc <code>{name}</code>.", del_in=5)
    return await _reply_filter(m, f"{E_CROSS} Không tìm thấy bộ lọc này.", del_in=5)


@app.on_message(
    filters.text & ~filters.private & ~filters.channel & ~filters.via_bot & ~filters.forwarded,
    group=103,
)
async def filters_re(_, message):
    try:
        from_user = message.from_user if message.from_user else message.sender_chat
    except AttributeError:
        return
    chat_id = message.chat.id
    text = message.text.lower().strip()
    if not text or (
        message.command and message.command[0].lower() in ["boloc", "themboloc"]
    ):
        return
    chat_id = message.chat.id
    list_of_filters = await get_filters_names(chat_id)
    for word in list_of_filters:
        pattern = r"( |^|[^\w])" + re.escape(word) + r"( |$|[^\w])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            _filter = await get_filter(chat_id, word)
            if _filter is False:
                continue
            data_type = _filter["type"]
            data = _filter.get("data")
            file_id = _filter.get("file_id")
            keyb = None
            if data is not None:
                if "{chat}" in data:
                    data = data.replace(
                        "{chat}", message.chat.title
                    )
                if "{name}" in data:
                    data = data.replace(
                        "{name}", (from_user.mention if message.from_user else from_user.title)
                    )
                if data and re.findall(r"\[.+\,.+\]", data):
                    keyboard = extract_text_and_keyb(ikb, data)
                    if keyboard:
                        data, keyb = keyboard
            replied_message = message.reply_to_message
            if replied_message:
                replied_user = replied_message.from_user if replied_message.from_user else replied_message.sender_chat
                if text.startswith("~"):
                    await message.delete()
                if replied_user and replied_user.id != from_user.id:
                    message = replied_message

            if data_type == "text":
                await message.reply_text(
                    text=(data or ""),
                    reply_markup=keyb,
                    disable_web_page_preview=True,
                )
                return
            if not file_id:
                continue
            try:
                if data_type == "sticker":
                    await message.reply_sticker(sticker=file_id)
                elif data_type == "animation":
                    await message.reply_animation(
                        animation=file_id,
                        caption=data,
                        reply_markup=keyb,
                    )
                elif data_type == "photo":
                    await message.reply_photo(
                        photo=file_id,
                        caption=data,
                        reply_markup=keyb,
                    )
                elif data_type == "document":
                    await message.reply_document(
                        document=file_id,
                        caption=data,
                        reply_markup=keyb,
                    )
                elif data_type == "video":
                    await message.reply_video(
                        video=file_id,
                        caption=data,
                        reply_markup=keyb,
                    )
                elif data_type == "video_note":
                    await message.reply_video_note(video_note=file_id)
                elif data_type == "audio":
                    await message.reply_audio(
                        audio=file_id,
                        caption=data,
                        reply_markup=keyb,
                    )
                elif data_type == "voice":
                    await message.reply_voice(
                        voice=file_id,
                        caption=data,
                        reply_markup=keyb,
                    )
            except Exception as e:
                LOGGER.warning("filters_re send failed: %s", e)
            return


@app.on_message(filters.command("xhboloc", COMMAND_HANDLER) & ~filters.private)
@adminsOnly("can_change_info")
async def stop_all(_, message):
    _filters = await get_filters_names(message.chat.id)
    if not _filters:
        return await _reply_filter(message, f"{E_NOTE} Không có bộ lọc trong cuộc trò chuyện này.")
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("OK, LÀM ĐI", callback_data="xboloc_yes"),
                InlineKeyboardButton("Huỷ", callback_data="xboloc_no"),
            ]
        ]
    )
    await _reply_filter(
        message,
        f"{E_WARN} <b>Xóa tất cả bộ lọc?</b>\nHành động này không thể hoàn tác.",
        reply_markup=keyboard,
    )


@app.on_callback_query(filters.regex("xboloc_(.*)"))
async def stop_all_cb(_, cb):
    chat_id = cb.message.chat.id
    from_user = cb.from_user
    permissions = await member_permissions(chat_id, from_user.id)
    permission = "can_change_info"
    if permission not in permissions:
        return await cb.answer(
            f"Bạn không có quyền cần thiết để thực hiện lệnh này.\nQuyền cần thiết: {permission}",
            show_alert=True,
        )
    inp = cb.data.split("_", 1)[1]
    await cb.answer()
    if inp == "yes":
        result = await deleteall_filters(chat_id)
        if result and result.deleted_count:
            await cb.message.edit(
                f"{E_SUCCESS} Đã xóa thành công tất cả bộ lọc trong cuộc trò chuyện này.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await cb.message.edit(
                f"{E_NOTE} Không có bộ lọc nào để xóa.",
                parse_mode=ParseMode.HTML,
            )
    elif inp == "no":
        if cb.message.reply_to_message:
            await cb.message.reply_to_message.delete()
        await cb.message.delete()
