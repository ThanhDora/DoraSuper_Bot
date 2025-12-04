import re
import logging
from logging import getLogger

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.filters_db import (
    delete_filter,
    deleteall_filters,
    get_filter,
    get_filters_names,
    save_filter,
)
from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.core.decorator.permissions import adminsOnly, member_permissions
from tiensiteo.core.keyboard import ikb
from tiensiteo.helper.functions import extract_text_and_keyb, extract_urls
from tiensiteo.vars import COMMAND_HANDLER

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "BộLọc"
__HELP__ = """
<blockquote>/xemboloc - Lấy tất cả các bộ lọc trong cuộc trò chuyện.
/boloc [TÊN_BỘ_LỌC] hoặc /themboloc [TÊN_BỘ_LỌC] - Lưu một bộ lọc (trả lời một tin nhắn).

Các loại bộ lọc được hỗ trợ là Văn bản, Hoạt hình, Ảnh, Tài liệu, Video, ghi chú video, Âm thanh, Giọng nói.

Để sử dụng nhiều từ trong một bộ lọc, hãy sử dụng
/boloc Hey_there hoặc /themboloc Hey_there để lọc "Hey there".
/xboloc [TÊN_BỘ_LỌC] hoặc /xoaboloc [TÊN_BỘ_LỌC] - Dừng một bộ lọc.
/xhboloc> - Xóa tất cả các bộ lọc trong một cuộc trò chuyện (vĩnh viễn).</blockquote>
"""


@app.on_message(
    filters.command(["themboloc", "boloc"], COMMAND_HANDLER) & ~filters.private
)
@adminsOnly("can_change_info")
async def save_filters(_, message):
    try:
        if len(message.command) < 2 or not message.reply_to_message:
            return await message.reply_text(
                "**Sử dụng:**\nTrả lời tin nhắn bằng /boloc [Tên bộ lọc] để thiết lập một bộ lọc mới."
            )
        text = message.text.markdown
        name = text.split(None, 1)[1].strip()
        if not name:
            return await message.reply_text("**Sử dụng:**\n__/boloc [FILTER_NAME]__")
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
            data = (
                replied_message.text.markdown
                if replied_message.text
                else replied_message.caption.markdown
            )
        if replied_message.text:
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
        if replied_message.reply_markup and not re.findall(r"\[.+\,.+\]", data):
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
        return await message.reply_text(f"__**Đã lưu bộ lọc {name}.**__")
    except UnboundLocalError:
        return await message.reply_text(
            "**Tin nhắn đã trả lời không thể truy cập được.\n`Chuyển tiếp tin nhắn và thử lại`**"
        )


@app.on_message(filters.command("xemboloc", COMMAND_HANDLER) & ~filters.private)
@capture_err
async def get_filterss(_, m):
    _filters = await get_filters_names(m.chat.id)
    if not _filters:
        return await m.reply_msg("**Không có bộ lọc nào trong cuộc trò chuyện này.**")
    _filters.sort()
    msg = f"Danh sách các bộ lọc trong {m.chat.title} {m.chat.id}\n"
    for _filter in _filters:
        msg += f"**-** `{_filter}`\n"
    await m.reply_msg(msg)


@app.on_message(
    filters.command(["xboloc", "xoaboloc"], COMMAND_HANDLER) & ~filters.private
)
@adminsOnly("can_change_info")
async def del_filter(_, m):
    if len(m.command) < 2:
        return await m.reply_msg("**Sử dụng:**\n__/xoaboloc [FILTER_NAME]__", del_in=6)
    name = m.text.split(None, 1)[1].strip()
    if not name:
        return await m.reply_msg("**Sử dụng:**\n__/xoaboloc [FILTER_NAME]__", del_in=6)
    chat_id = m.chat.id
    deleted = await delete_filter(chat_id, name)
    if deleted:
        return await m.reply_msg(f"**Đã xoá bộ lọc {name}.**")
    else:
        return await m.reply_msg("**Không có bộ lọc.**")


@app.on_message(
    filters.text & ~filters.private & ~filters.channel & ~filters.via_bot & ~filters.forwarded,
    group=103,
)
async def filters_re(self, message):
    try:
        from_user = message.from_user if message.from_user else message.sender_chat
        user_id = from_user.id
    except AttributeError:
        self.log.info(message)
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
            data_type = _filter["type"]
            data = _filter.get("data")
            file_id = _filter.get("file_id")
            keyb = None
            if data:
                if "{chat}" in data:
                    data = data.replace(
                        "{chat}", message.chat.title
                    )
                if "{name}" in data:
                    data = data.replace(
                        "{name}", (from_user.mention if message.from_user else from_user.title)
                    )
                if re.findall(r"\[.+\,.+\]", data):
                    keyboard = extract_text_and_keyb(ikb, data)
                    if keyboard:
                        data, keyb = keyboard
            replied_message = message.reply_to_message
            if replied_message:
                replied_user = replied_message.from_user if replied_message.from_user else replied_message.sender_chat
                if text.startswith("~"):
                    await message.delete()
                if replied_user.id != from_user.id:
                    message = replied_message

            if data_type == "text":
                await message.reply_text(
                    text=data,
                    reply_markup=keyb,
                    disable_web_page_preview=True,
                )
            else:
                if not file_id:
                    continue
            if data_type == "sticker":
                await message.reply_sticker(
                    sticker=file_id,
                )
            if data_type == "animation":
                await message.reply_animation(
                    animation=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            if data_type == "photo":
                await message.reply_photo(
                    photo=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            if data_type == "document":
                await message.reply_document(
                    document=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            if data_type == "video":
                await message.reply_video(
                    video=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            if data_type == "video_note":
                await message.reply_video_note(
                    video_note=file_id,
                )
            if data_type == "audio":
                await message.reply_audio(
                    audio=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            if data_type == "voice":
                await message.reply_voice(
                    voice=file_id,
                    caption=data,
                    reply_markup=keyb,
                )
            return


@app.on_message(filters.command("xhboloc", COMMAND_HANDLER) & ~filters.private)
@adminsOnly("can_change_info")
async def stop_all(_, message):
    _filters = await get_filters_names(message.chat.id)
    if not _filters:
        await message.reply_text("**Không có bộ lọc trong cuộc trò chuyện này.**")
    else:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("OK, LÀM ĐI", callback_data="xboloc_yes"),
                    InlineKeyboardButton("Huỷ", callback_data="xboloc_no"),
                ]
            ]
        )
        await message.reply_text(
            "**Bạn có chắc chắn muốn xóa tất cả các bộ lọc trong cuộc trò chuyện này mãi mãi không ?.**",
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
            f"Bạn không có các quyền bắt buộc.\n Quyền cần thiết: {permission}",
            show_alert=True,
        )
    input = cb.data.split("_", 1)[1]
    if input == "yes":
        stoped_all = await deleteall_filters(chat_id)
        if stoped_all:
            return await cb.message.edit(
                "**Đã xóa thành công tất cả các bộ lọc trên cuộc trò chuyện này.**"
            )
    if input == "no":
        await cb.message.reply_to_message.delete()
        await cb.message.delete()
