from re import findall

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.notes_db import (
    delete_note,
    deleteall_notes,
    get_note,
    get_note_names,
    save_note,
)
from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.core.decorator.permissions import adminsOnly, member_permissions
from tiensiteo.core.keyboard import ikb
from tiensiteo.helper.functions import extract_text_and_keyb, extract_urls
from tiensiteo.vars import COMMAND_HANDLER

__MODULE__ = "GhiChú"
__HELP__ = """
<blockquote>/notes - Lấy tất cả các ghi chú trong cuộc trò chuyện.

/save [TÊN_GHI_CHÚ] hoặc /addnote [TÊN_GHI_CHÚ] - Lưu một ghi chú.

Các loại ghi chú được hỗ trợ bao gồm Văn bản, Hoạt hình, Ảnh, Tài liệu, Video, ghi chú video, Âm thanh, Giọng nói.

Để thay đổi chú thích của bất kỳ tệp nào, sử dụng:
/save [TÊN_GHI_CHÚ] hoặc /addnote [TÊN_GHI_CHÚ] [CHÚ THÍCH_MỚI].

#TÊN_GHI_CHÚ - Để lấy một ghi chú.

/delete [TÊN_GHI_CHÚ] hoặc /delnote [TÊN_GHI_CHÚ] - Xóa một ghi chú.
/deleteall - Xóa tất cả các ghi chú trong một cuộc trò chuyện (vĩnh viễn).</blockquote>
"""


@app.on_message(
    filters.command(["addnote", "save"], COMMAND_HANDLER) & ~filters.private
)
@adminsOnly("can_change_info")
async def save_notee(_, message):
    try:
        if len(message.command) < 2 or not message.reply_to_message:
            await message.reply_msg(
                "**Usage:**\nTrả lời tin nhắn bằng /save [NOTE_NAME] để lưu một ghi chú mới."
            )
        else:
            text = message.text.markdown
            name = text.split(None, 1)[1].strip()
            if not name:
                return await message.reply_msg("**Sử dụng**\n__/save [Tên_ghi_chú]__")
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
            if replied_message.reply_markup and not findall(r"\[.+\,.+\]", data):
                if urls := extract_urls(replied_message.reply_markup):
                    response = "\n".join(
                        [f"{name}=[{text}, {url}]" for name, text, url in urls]
                    )
                    data = data + response
            note = {
                "type": _type,
                "data": data,
                "file_id": file_id,
            }
            prefix = message.text.split()[0][0]
            chat_id = message.chat.id
            await save_note(chat_id, name, note)
            await message.reply_msg(f"__**Đã lưu ghi chú {name}.**__")
    except UnboundLocalError:
        return await message.reply_text(
            "**Tin nhắn đã trả lời không thể truy cập được.\n`Chuyển tiếp tin nhắn và thử lại`**"
        )


@app.on_message(filters.command("notes", COMMAND_HANDLER) & ~filters.private)
@capture_err
async def get_notes(_, message):
    chat_id = message.chat.id
    _notes = await get_note_names(chat_id)

    if not _notes:
        return await message.reply("**Không có ghi chú nào trong cuộc trò chuyện này.**")
    _notes.sort()
    msg = f"Danh sách ghi chú trong nhóm {message.chat.title} - {message.chat.id}\n"
    for note in _notes:
        msg += f"**-** `{note}`\n"
    await message.reply(msg)


@app.on_message(filters.regex(r"^#.+") & filters.text & ~filters.private)
@capture_err
async def get_one_note(_, message):
    from_user = message.from_user if message.from_user else message.sender_chat
    chat_id = message.chat.id
    name = message.text.replace("#", "", 1)
    if not name:
        return
    _note = await get_note(chat_id, name)
    if not _note:
        return
    type = _note.get("type")
    data = _note.get("data")
    file_id = _note.get("file_id")
    keyb = None
    if data:
        if "{chat}" in data:
            data = data.replace("{chat}", message.chat.title)
        if "{name}" in data:
            data = data.replace(
                "{name}", (from_user.mention if message.from_user else from_user.title)
            )
        if findall(r"\[.+\,.+\]", data):
            keyboard = extract_text_and_keyb(ikb, data)
            if keyboard:
                data, keyb = keyboard
    replied_message = message.reply_to_message
    if replied_message:
        replied_user = replied_message.from_user if replied_message.from_user else replied_message.sender_chat
        if replied_user.id != from_user.id:
            message = replied_message
    if type == "text":
        await message.reply_text(
            text=data,
            reply_markup=keyb,
            disable_web_page_preview=True,
        )
    if type == "sticker":
        await message.reply_sticker(
            sticker=file_id,
        )
    if type == "animation":
        await message.reply_animation(
            animation=file_id,
            caption=data,
            reply_markup=keyb,
        )
    if type == "photo":
        await message.reply_photo(
            photo=file_id,
            caption=data,
            reply_markup=keyb,
        )
    if type == "document":
        await message.reply_document(
            document=file_id,
            caption=data,
            reply_markup=keyb,
        )
    if type == "video":
        await message.reply_video(
            video=file_id,
            caption=data,
            reply_markup=keyb,
        )
    if type == "video_note":
        await message.reply_video_note(
            video_note=file_id,
        )
    if type == "audio":
        await message.reply_audio(
            audio=file_id,
            caption=data,
            reply_markup=keyb,
        )
    if type == "voice":
        await message.reply_voice(
            voice=file_id,
            caption=data,
            reply_markup=keyb,
        )


@app.on_message(
    filters.command(["delnote", "clear"], COMMAND_HANDLER) & ~filters.private
)
@adminsOnly("can_change_info")
async def del_note(_, message):
    if len(message.command) < 2:
        return await message.reply_msg("**Cách sử dụng**\n__/delete [NOTE_NAME]__")
    name = message.text.split(None, 1)[1].strip()
    if not name:
        return await message.reply_msg("**Cách sử dụng**\n__/delete [NOTE_NAME]__")

    prefix = message.text.split()[0][0]
    chat_id = message.chat.id

    deleted = await delete_note(chat_id, name)
    if deleted:
        await message.reply_msg(f"**Ghi chú đã xóa {name} thành công.**")
    else:
        await message.reply_msg("**Không có ghi chú như vậy.**")


@app.on_message(filters.command("deleteall", COMMAND_HANDLER) & ~filters.private)
@adminsOnly("can_change_info")
async def delete_all(_, message):
    _notes = await get_note_names(message.chat.id)
    if not _notes:
        return await message.reply_text("**Không có ghi chú nào trong cuộc trò chuyện này.**")
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Vâng, hãy làm đi", callback_data="delete_yes"),
                InlineKeyboardButton("Hủy", callback_data="delete_no"),
            ]
        ]
    )
    await message.reply_text(
        "**Bạn có chắc chắn muốn xóa tất cả ghi chú trong cuộc trò chuyện này mãi mãi không?.**",
        reply_markup=keyboard,
    )


@app.on_callback_query(filters.regex("delete_(.*)"))
async def delete_all_cb(_, cb):
    chat_id = cb.message.chat.id
    from_user = cb.from_user
    permissions = await member_permissions(chat_id, from_user.id)
    permission = "can_change_info"
    if permission not in permissions:
        return await cb.answer(
            f"Bạn không có quyền cần thiết.\n Quyền cần thiết: {permission}",
            show_alert=True,
        )
    input = cb.data.split("_", 1)[1]
    if input == "yes":
        stoped_all = await deleteall_notes(chat_id)
        if stoped_all:
            return await cb.message.edit(
                "**Đã xóa thành công tất cả ghi chú trên cuộc trò chuyện này.**"
            )
