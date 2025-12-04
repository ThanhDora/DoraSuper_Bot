import os
import logging
from logging import getLogger

from PIL import Image, ImageDraw, ImageFont
from pyrogram import filters

from tiensiteo import app
from tiensiteo.vars import COMMAND_HANDLER

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "ViếtTay"
__HELP__ = """
<blockquote>/viettay [trả lời tin nhắn hoặc viết sau lệnh] - Dành cho những ai lười viết, sẽ tự động tạo một trang chữ viết tay.</blockquote>
"""


def text_set(text):
    lines = []
    max_length = 75  # Độ dài tối đa của mỗi dòng

    all_lines = text.split("\n")
    for line in all_lines:
        words = line.split()  # Tách dòng thành các từ
        current_line = ""
        for word in words:
            # Nếu thêm từ này vào dòng hiện tại mà vượt quá độ dài tối đa
            if len(current_line) + len(word) + 1 > max_length:
                lines.append(current_line.strip())  # Thêm dòng hiện tại vào danh sách
                current_line = word + " "  # Bắt đầu dòng mới với từ này
            else:
                current_line += word + " "  # Thêm từ vào dòng hiện tại

        # Thêm dòng cuối cùng vào danh sách nếu có
        if current_line:
            lines.append(current_line.strip())

    return lines[:25]  # Giới hạn trả về 25 dòng đầu tiên




@app.on_message(filters.command(["viettay"], COMMAND_HANDLER))
async def handwrite(client, message):
    if message.reply_to_message and message.reply_to_message.text:
        txt = message.reply_to_message.text
    elif len(message.command) > 1:
        txt = message.text.split(None, 1)[1]
    else:
        return await message.reply(
            "Vui lòng trả lời tin nhắn hoặc viết nội dung sau lệnh để sử dụng."
        )
    nan = await message.reply_msg("Đang xử lý...")
    try:
        img = Image.open("assets/giayviet.jpg")
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype("assets/QwitcherGrypen-Regular.ttf", 40)
        x, y = 160, 120
        lines = text_set(txt)
        line_height = font.getbbox("hg")[3]
        for line in lines:
            draw.text((x, y), line, fill=(1, 22, 55), font=font)
            y = y + line_height - 5
        file = f"nulis_{message.from_user.id}.jpg"
        img.save(file)
        if os.path.exists(file):
            await message.reply_photo(
                photo=file, caption=f"<b>Viết bởi :</b> {client.me.mention}"
            )
            os.remove(file)
            await nan.delete()
    except Exception as e:
        return await message.reply(e)
