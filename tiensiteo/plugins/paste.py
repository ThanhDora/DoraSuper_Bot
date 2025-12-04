import logging
from logging import getLogger

from json import loads as json_loads
from os import remove
from re import compile as compiles

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tiensiteo import app
from tiensiteo.helper import fetch, post_to_telegraph, rentry
from tiensiteo.vars import COMMAND_HANDLER

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "CôngCụDán"
__HELP__ = """
<blockquote>/paste [Văn bản/Trả lời tin nhắn] - Đăng văn bản lên Rentry có hỗ trợ markdown.

/tgraph [Văn bản/Trả lời tin nhắn] - Đăng văn bản và tạo trang trên Telegraph.

/sbin [Văn bản/Trả lời tin nhắn] - Đăng văn bản lên Spacebin.

/ybin [Văn bản/Trả lời tin nhắn] - Đăng văn bản lên Pastebin.</blockquote>
"""


# Size Checker for Limit
def humanbytes(size: int):
    """Chuyển Đổi Byte Thành Byte Để Con Người Có Thể Đọc Nó"""
    if not isinstance(size, int):
        try:
            pass
        except ValueError:
            size = None
    if not size:
        return "0 B"
    size = int(size)
    power = 2**10
    raised_to_pow = 0
    dict_power_n = {
        0: "",
        1: "K",
        2: "M",
        3: "G",
        4: "T",
        5: "P",
        6: "E",
        7: "Z",
        8: "Y",
    }
    while size > power:
        size /= power
        raised_to_pow += 1
    try:
        real_size = f"{str(round(size, 2))} {dict_power_n[raised_to_pow]}B"
    except KeyError:
        real_size = "Không thể xác định kích thước thực !"
    return real_size


# Pattern if extension supported, PR if want to add more
pattern = compiles(r"^text/|json$|yaml$|xml$|toml$|x-sh$|x-shellscript$|x-subrip$")


@app.on_message(filters.command(["tgraph"], COMMAND_HANDLER))
async def telegraph_paste(_, message):
    reply = message.reply_to_message
    if not reply and len(message.command) < 2:
        return await message.reply_msg(
            f"**Trả lời một tin nhắn với /{message.command[0]} hoặc với lệnh**",
            del_in=6,
        )

    if message.from_user:
        if message.from_user.username:
            uname = f"@{message.from_user.username} [{message.from_user.id}]"
        else:
            uname = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id}) [{message.from_user.id}]"
    else:
        uname = message.sender_chat.title
    
    msg = await message.reply_msg("`Đang dán vào Telegraph...`")

    # Xử lý trường hợp tin nhắn trả lời có văn bản
    if reply.text:
        title = message.text.split(None, 1)[1] if len(message.command) > 1 else "Tiến Sĩ Tèo"
        data = reply.text.html.replace("\n", "<br>")
    # Xử lý trường hợp tin nhắn trả lời có caption của ảnh hoặc video
    elif reply.caption:
        title = message.text.split(None, 1)[1] if len(message.command) > 1 else "Tiến Sĩ Tèo"
        data = reply.caption.html.replace("\n", "<br>")
    # Nếu không có văn bản và không có caption, gửi thông báo lỗi
    elif not reply and len(message.command) >= 2:
        title = "Tiến Sĩ Tèo"
        data = message.text.split(None, 1)[1]
    else:
        return await msg.edit_msg("**Chỉ có văn bản hoặc mô tả ảnh/video mới được hỗ trợ.**")

    try:
        url = await post_to_telegraph(False, title, data)
    except Exception as e:
        return await msg.edit_msg(f"ERROR: {e}")

    if not url:
        return await msg.edit_msg("Văn bản quá ngắn hoặc gặp vấn đề với việc tải lên")

    button = [
        [InlineKeyboardButton("Mở liên kết", url=url)],
        [
            InlineKeyboardButton(
                "Chia sẻ liên kết", url=f"https://telegram.me/share/url?url={url}"
            )
        ],
    ]

    pasted = f"**Dán thành công dữ liệu của bạn lên Telegraph<a href='{url}'>.</a>\n\nPaste by {uname}**"
    await msg.edit_msg(pasted, reply_markup=InlineKeyboardMarkup(button))


# Default Paste to Wastebin using Deta
@app.on_message(filters.command(["ybin"], COMMAND_HANDLER))
async def wastepaste(_, message):
    reply = message.reply_to_message
    target = str(message.command[0]).split("@", maxsplit=1)[0]
    if not reply and len(message.command) < 2:
        return await message.reply_msg(
            f"**Trả lời một tin nhắn với /{target} hoặc với lệnh**", del_in=6
        )

    msg = await message.reply_msg("`Đang dán vào YasirBin...`")
    data = ""
    limit = 1024 * 1024
    if reply and reply.document:
        if reply.document.file_size > limit:
            return await msg.edit_msg(
                f"**Bạn chỉ có thẻ dán tệp nhỏ hơn {humanbytes(limit)}.**"
            )
        if not pattern.search(reply.document.mime_type):
            return await msg.edit_msg("**Chỉ có văn bản được hỗ trợ.**")
        file = await reply.download()
        try:
            with open(file, "r") as text:
                data = text.read()
            remove(file)
        except UnicodeDecodeError:
            try:
                remove(file)
            except:
                pass
            return await msg.edit_msg("`Tệp không hỗ trợ !`")
    elif reply and (reply.text or reply.caption):
        data = reply.text or reply.caption
    elif not reply and len(message.command) >= 2:
        data = message.text.split(None, 1)[1]

    if message.from_user:
        if message.from_user.username:
            uname = f"@{message.from_user.username} [{message.from_user.id}]"
        else:
            uname = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id}) [{message.from_user.id}]"
    else:
        uname = message.sender_chat.title

    try:
        json_data = {
            "content": data,
            "highlighting_language": "auto",
            "ephemeral": False,
            "expire_at": 0,
            "expire_in": 0,
        }
        response = await fetch.post(
            "https://paste.yasir.eu.org/api/new", json=json_data
        )
        url = f"https://paste.yasir.eu.org/{response.json()['id']}"
    except Exception as e:
        return await msg.edit_msg(f"ERROR: {e}")

    if not url:
        return await msg.edit_msg("Văn Bản Quá Ngắn Hoặc Các Vấn Đề Về Tệp")
    button = [
        [InlineKeyboardButton("Mở liên kết", url=url)],
        [
            InlineKeyboardButton(
                "Chia sẻ liên kết", url=f"https://telegram.me/share/url?url={url}"
            )
        ],
    ]

    pasted = f"**Dán thành công dữ liệu của bạn đến YasirBin<a href='{url}'>.</a>\n\nPaste by {uname}**"
    await msg.edit_msg(pasted, reply_markup=InlineKeyboardMarkup(button))



# Paste as spacebin
@app.on_message(filters.command(["sbin"], COMMAND_HANDLER))
async def spacebinn(_, message):
    reply = message.reply_to_message
    target = str(message.command[0]).split("@", maxsplit=1)[0]
    if not reply and len(message.command) < 2:
        return await message.reply_msg(
            f"**Trả lời một tin nhắn với /{target} hoặc với lệnh**", del_in=6
        )

    msg = await message.reply_msg("`Đang dán vào Spacebin...`")
    data = ""
    
    # Xử lý văn bản từ tin nhắn trả lời
    if reply.text:
        data = reply.text.html
    # Xử lý caption của ảnh hoặc video
    elif reply.caption:
        data = reply.caption.html
    # Xử lý văn bản từ lệnh nếu không có tin nhắn trả lời
    elif not reply and len(message.command) >= 2:
        data = message.text.split(None, 1)[1]
    else:
        return await msg.edit_msg("**Chỉ có văn bản hoặc mô tả ảnh/video mới được hỗ trợ.**")

    if message.from_user:
        if message.from_user.username:
            uname = f"@{message.from_user.username}"
        else:
            uname = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})"
    else:
        uname = message.sender_chat.title

    try:
        siteurl = "https://spaceb.in/api/"
        response = await fetch.post(siteurl, json={"content": data, "extension": "txt"})
        response = response.json()
        url = "https://spaceb.in/" + response["payload"]["id"]
    except Exception as e:
        return await msg.edit_msg(f"ERROR: {e}")

    if not url:
        return await msg.edit_msg("Văn bản quá ngắn hoặc gặp vấn đề với việc tải lên")

    button = [
        [InlineKeyboardButton("Mở liên kết", url=url)],
        [
            InlineKeyboardButton(
                "Chia sẻ liên kết", url=f"https://telegram.me/share/url?url={url}"
            )
        ],
    ]

    pasted = f"**Dán thành công dữ liệu của bạn đến Spacebin<a href='{url}'>.</a>\n\nPaste by {uname}**"
    await msg.edit_msg(pasted, reply_markup=InlineKeyboardMarkup(button))


# Rentry paste
@app.on_message(filters.command(["paste"], COMMAND_HANDLER))
async def rentrypaste(_, message):
    reply = message.reply_to_message
    target = str(message.command[0]).split("@", maxsplit=1)[0]
    if not reply and len(message.command) < 2:
        return await message.reply_msg(
            f"**Trả lời một tin nhắn với /{target} hoặc với lệnh**", del_in=6
        )

    msg = await message.reply_msg("`Đang dán vào Rentry...`")
    data = ""
    
    # Xử lý văn bản từ tin nhắn trả lời
    if reply.text:
        data = reply.text.markdown
    # Xử lý caption của ảnh hoặc video
    elif reply.caption:
        data = reply.caption.markdown
    # Xử lý văn bản từ lệnh nếu không có tin nhắn trả lời
    elif not reply and len(message.command) >= 2:
        data = message.text.split(None, 1)[1]
    else:
        return await msg.edit_msg("**Chỉ có văn bản hoặc mô tả ảnh/video mới được hỗ trợ.**")

    if message.from_user:
        if message.from_user.username:
            uname = f"@{message.from_user.username}"
        else:
            uname = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})"
    else:
        uname = message.sender_chat.title

    try:
        url = await rentry(data)
    except Exception as e:
        return await msg.edit_msg(f"`{e}`")

    if not url:
        return await msg.edit_msg("Văn bản quá ngắn hoặc gặp vấn đề với việc tải lên")

    button = [
        [InlineKeyboardButton("Mở liên kết", url=url)],
        [
            InlineKeyboardButton(
                "Chia sẻ liên kết", url=f"https://telegram.me/share/url?url={url}"
            )
        ],
    ]

    pasted = f"**Dán thành công dữ liệu của bạn đến Rentry<a href='{url}'>.</a>\n\nPaste by {uname}**"
    await msg.edit_msg(pasted, reply_markup=InlineKeyboardMarkup(button))