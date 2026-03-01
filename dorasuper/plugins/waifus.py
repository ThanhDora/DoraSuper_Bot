import requests
import logging
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message
from dorasuper import app
from dorasuper.emoji import E_ERROR, E_LIMIT, E_LOADING
from dorasuper.core.decorator.errors import capture_err
from dorasuper.vars import COMMAND_HANDLER
from database.funny_db import can_use_command, update_user_command_usage

LOGGER = getLogger("DoraSuper")

__MODULE__ = "HHTươngTác"
__HELP__ = (
    "<blockquote>/punch, /slap, /lick, /kill, /hug, /bite, /kiss, /highfive, /die, /run, /shoot, /dance [trả lời một tin nhắn hoặc không] - Gửi ảnh động tương tác.</blockquote>"
)

# Danh sách lệnh và thông tin tương ứng
COMMANDS = {
    "punch": {"emoji": "💥", "text": "đấm"},
    "slap": {"emoji": "😒", "text": "tát"},
    "lick": {"emoji": "😛", "text": "liếm"},
    "kill": {"emoji": "😵", "text": "giết"},
    "hug": {"emoji": "🤗", "text": "ôm"},
    "bite": {"emoji": "😈", "text": "cắn"},
    "kiss": {"emoji": "😘", "text": "hôn"},
    "highfive": {"emoji": "🙌", "text": "đập tay"},
    "die": {"emoji": "💀", "text": "chết"},
    "run": {"emoji": "🏃", "text": "chạy"},
    "shoot": {"emoji": "🔫", "text": "bắn"},
    "dance": {"emoji": "💃", "text": "nhảy"}
}

async def get_animation(api_token, animation_type):
    url = f"https://waifu.it/api/v4/{animation_type}"
    headers = {"Authorization": api_token}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get("url")
    except requests.exceptions.RequestException as e:
        LOGGER.error(f"Failed to fetch animation for {animation_type}: {str(e)}")
        return None

@app.on_message(
    filters.command(list(COMMANDS.keys()), COMMAND_HANDLER)
    & ~filters.forwarded
    & ~filters.via_bot
)
@capture_err
async def animation_command(_, ctx: Message):
    # Phản hồi ngay lập tức khi nhận lệnh
    msg = await ctx.reply_msg(f"{E_LOADING} Đang xử lý ảnh động...", quote=True)

    try:
        # Validate sender
        if not ctx.from_user:
            await msg.edit_msg(f"{E_ERROR} Lệnh này chỉ dành cho người dùng, không phải kênh hoặc nhóm ẩn danh!")
            return

        # Get sender and chat info
        sender_id = ctx.from_user.id
        sender = ctx.from_user.mention(style="markdown")
        chat_id = ctx.chat.id
        command = ctx.command[0].lower()

        # Check if sender can use the command
        if not await can_use_command(chat_id, sender_id, command):
            await msg.edit_msg(
                f"{E_ERROR} Bạn đã sử dụng lệnh /{command} hôm nay. Hãy thử lại vào ngày mai!",
                parse_mode=enums.ParseMode.HTML,
            )
            return

        # Determine target
        target = sender
        if ctx.reply_to_message:
            target = (
                ctx.reply_to_message.from_user.mention(style="markdown")
                if ctx.reply_to_message.from_user
                else ctx.reply_to_message.sender_chat.title
            )

        # Fetch animation
        api_token = ""  # Replace with secure token storage
        gif_url = await get_animation(api_token, command)

        if gif_url:
            caption = f"{sender} {COMMANDS[command]['text']} {target}! {COMMANDS[command]['emoji']}"
            await ctx.reply_animation(animation=gif_url, caption=caption, quote=True)
            # Update sender's command usage
            await update_user_command_usage(chat_id, sender_id, command)
            await msg.delete()
        else:
            await msg.edit_msg(f"{E_ERROR} Không thể lấy ảnh động. Vui lòng thử lại sau!")
    except Exception as e:
        LOGGER.error(f"Error in {command} command: {str(e)}")
        await msg.edit_msg(f"{E_ERROR} Lỗi, vui lòng thử lại sau! 😔")