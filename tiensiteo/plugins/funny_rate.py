import random
import logging
from logging import getLogger
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.vars import COMMAND_HANDLER
from database.funny_db import can_use_command, update_user_command_usage

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "ĐánhGiáVui"
__HELP__ = """
<blockquote>/cutie - Đánh giá mức độ dễ thương của bạn hoặc người được trả lời.
/hot - Đánh giá mức độ nóng bỏng của bạn hoặc người được trả lời.
/horny - Đánh giá mức độ... tò mò của bạn hoặc người được trả lời.
/sexy - Đánh giá mức độ quyến rũ của bạn hoặc người được trả lời.
/gay - Đánh giá mức độ gay của bạn hoặc người được trả lời.
/lesbian - Đánh giá mức độ lesbian của bạn hoặc người được trả lời.
/boob - Đánh giá kích thước... của bạn hoặc người được trả lời.
/cock - Đánh giá kích thước... của bạn hoặc người được trả lời.</blockquote>
"""

# Định nghĩa các link media
MEDIA = {
    "cutie": "https://graph.org/file/24375c6e54609c0e4621c.mp4",
    "hot": "https://graph.org/file/745ba3ff07c1270958588.mp4",
    "horny": "https://graph.org/file/eaa834a1cbfad29bd1fe4.mp4",
    "sexy": "https://graph.org/file/58da22eb737af2f8963e6.mp4",
    "gay": "https://graph.org/file/850290f1f974c5421ce54.mp4",
    "lesbian": "https://graph.org/file/ff258085cf31f5385db8a.mp4",
    "boob": "https://i.gifer.com/8ZUg.gif",
    "cock": "https://telegra.ph/file/423414459345bf18310f5.gif"
}

# Nút hỗ trợ
BUTTON = [[InlineKeyboardButton("Ủng Hộ", url="https://dabeecao.org#donate")]]

# Hàm chung để xử lý các lệnh
async def handle_fun_command(ctx, command, caption_template, emoji):
    try:
        # Lấy thông tin người dùng
        chat_id = ctx.chat.id
        sender_id = ctx.from_user.id  # Always track usage for the sender
        if ctx.reply_to_message:
            user_id = ctx.reply_to_message.from_user.id
            user_name = ctx.reply_to_message.from_user.first_name
        else:
            user_id = ctx.from_user.id
            user_name = ctx.from_user.first_name

        # Kiểm tra xem người gửi có thể sử dụng lệnh không
        if not await can_use_command(chat_id, sender_id, command):
            await ctx.reply_msg(
                f"🚫 Bạn đã sử dụng lệnh /{command} hôm nay. Hãy thử lại vào ngày mai! 😊",
                quote=True
            )
            return

        mention = f"[{user_name}](tg://user?id={user_id})"
        percentage = random.randint(1, 100)
        
        # Tùy chỉnh caption theo lệnh
        if command in ["boob", "cock"]:
            caption = caption_template.format(mention=mention, value=percentage)
        else:
            caption = caption_template.format(mention=mention, value=percentage)

        # Gửi media và caption
        await app.send_document(
            chat_id=ctx.chat.id,
            document=MEDIA[command],
            caption=caption,
            reply_markup=InlineKeyboardMarkup(BUTTON),
            reply_to_message_id=ctx.reply_to_message.id if ctx.reply_to_message else ctx.id
        )

        # Cập nhật dữ liệu sử dụng lệnh cho người gửi
        await update_user_command_usage(chat_id, sender_id, command)

    except Exception as e:
        await ctx.reply_msg(f"Lỗi, vui lòng thử lại sau.", quote=True)

# Định nghĩa các lệnh
@app.on_message(filters.command(["cutie"], COMMAND_HANDLER))
@capture_err
async def cutie(_, ctx):
    await handle_fun_command(ctx, "cutie", "🍑 {mention} dễ thương {value}% nhé! 🥀", "🍑")

@app.on_message(filters.command(["hot"], COMMAND_HANDLER))
@capture_err
async def hot(_, ctx):
    await handle_fun_command(ctx, "hot", "🔥 {mention} nóng bỏng {value}%! 🔥", "🔥")

@app.on_message(filters.command(["horny"], COMMAND_HANDLER))
@capture_err
async def horny(_, ctx):
    await handle_fun_command(ctx, "horny", "🔥 {mention} tò mò {value}% nha! 😏", "🔥")

@app.on_message(filters.command(["sexy"], COMMAND_HANDLER))
@capture_err
async def sexy(_, ctx):
    await handle_fun_command(ctx, "sexy", "🔥 {mention} quyến rũ {value}%! 😘", "🔥")

@app.on_message(filters.command(["gay"], COMMAND_HANDLER))
@capture_err
async def gay(_, ctx):
    await handle_fun_command(ctx, "gay", "🍷 {mention} gay {value}% nè! 🏳️‍🌈", "🍷")

@app.on_message(filters.command(["lesbian"], COMMAND_HANDLER))
@capture_err
async def lesbian(_, ctx):
    await handle_fun_command(ctx, "lesbian", "💜 {mention} lesbian {value}% đó! 🏳️‍🌈", "💜")

@app.on_message(filters.command(["boob"], COMMAND_HANDLER))
@capture_err
async def boob(_, ctx):
    await handle_fun_command(ctx, "boob", "🍒 Kích thước ngực của {mention} là {value}! 😜", "🍒")

@app.on_message(filters.command(["cock"], COMMAND_HANDLER))
@capture_err
async def cock(_, ctx):
    await handle_fun_command(ctx, "cock", "🍆 Kích thước của {mention} là {value}cm! 😎", "🍆")