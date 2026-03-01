import random
import os
import logging
from logging import getLogger
from datetime import datetime
from pyrogram import filters
from pyrogram.types import Message
from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.vars import COMMAND_HANDLER
from database.funny_db import can_use_command, update_user_command_usage

LOGGER = getLogger("DoraSuper")

__MODULE__ = "YêuGhét"
__HELP__ = """
<blockquote>/love [tên hoặc trả lời tin nhắn] - Tính toán phần trăm tình yêu giữa bạn và người được chỉ định hoặc người bạn trả lời.
/hate [tên hoặc trả lời tin nhắn] - Tính toán mức độ "ghét" giữa bạn và người được chỉ định hoặc người bạn trả lời.</blockquote>
"""

def get_random_love_message(love_percentage):
    if love_percentage <= 20:
        return random.choice(
            [
                "Tình yêu còn mờ nhạt, cần thêm chút phép màu để tỏa sáng! ✨",
                "Chỉ là một tia sáng nhỏ, hãy thổi bùng ngọn lửa tình đi nào! 🔥",
                "Hơi lạnh nhạt, nhưng mọi chuyện tình đều bắt đầu từ đây! ❄️",
                "Tình cảm mới nhen nhóm, hãy kiên nhẫn nhé! 🌱",
                "Chút rung động ban đầu, nhưng tương lai còn nhiều bất ngờ! 💫",
            ]
        )
    elif love_percentage <= 40:
        return random.choice(
            [
                "Tình yêu đang lấp ló, hãy mở lòng để nó nở hoa! 🌸",
                "Có chút gì đó ngọt ngào, nhưng cần thêm thời gian để chín muồi! 🍬",
                "Trái tim bắt đầu rung rinh, cứ tiếp tục là sẽ bùng nổ! 💗",
                "Một khởi đầu đầy hứa hẹn, hãy cùng viết câu chuyện tình! 📖",
                "Tình cảm đang lớn dần, chỉ cần chút chăm sóc là đủ! 🌷",
            ]
        )
    elif love_percentage <= 60:
        return random.choice(
            [
                "Tình yêu đang ấm lên, hãy giữ lửa để nó cháy mãi! 🔥",
                "Hai trái tim đang hòa nhịp, cứ thế này là ngọt ngào lắm! 💖",
                "Kết nối khá mạnh, chỉ cần chút gia vị để hoàn hảo! 🌟",
                "Tình cảm đang nở rộ, hãy cùng nhau làm nó thêm đặc biệt! 🌺",
                "Cảm xúc dâng trào, chuyện tình này sắp thành cổ tích rồi! 🏰",
            ]
        )
    elif love_percentage <= 80:
        return random.choice(
            [
                "Wow, tình yêu mãnh liệt, hai bạn sinh ra để dành cho nhau! 💞",
                "Trái tim hòa quyện, chuyện tình này đẹp như một bài thơ! 📜",
                "Tình yêu bùng cháy, hãy giữ để nó mãi rực rỡ nhé! 🔥",
                "Cặp đôi hoàn hảo, chỉ cần nhìn là biết định mệnh! 🌹",
                "Hạnh phúc ngập tràn, tình yêu này đáng để trân trọng! 💍",
            ]
        )
    else:
        return random.choice(
            [
                "Trời ơi, tình yêu đỉnh cao, hai bạn là cặp đôi huyền thoại! 💎",
                "Tình yêu vĩnh cửu, không gì có thể chia cắt hai bạn! 💖",
                "Định mệnh an bài, hai trái tim này sinh ra để thuộc về nhau! 🌌",
                "Hoàn hảo tuyệt đối, chuyện tình này làm cả thế giới ghen tị! 😍",
                "Tình yêu vượt thời gian, mãi mãi là của nhau! ⏳",
            ]
        )

def get_random_hate_message(hate_percentage):
    if hate_percentage <= 20:
        return random.choice(
            [
                "Hơi khó chịu thôi, nhưng chắc tui lờ đi được... tạm thời! 😒",
                "Nhìn là muốn tránh xa, mà sao cứ lởn vởn trước mặt thế? 😣",
                "Ghét nhẹ nhẹ, kiểu như thấy bạn là mắt tui tự lườm! 😑",
                "Chỉ muốn nói 'tránh xa tui ra', nhưng thôi, để lần sau! 😤",
                "Hơi bực mình, nhưng tui kiềm chế được... lần này thôi nhé! 😖",
            ]
        )
    elif hate_percentage <= 40:
        return random.choice(
            [
                "Ghét vừa vừa, nhưng mỗi lần thấy bạn là tui muốn đổi tần số sống! 😣",
                "Bạn làm tui ngứa mắt ghê, kiểu muốn block mà chưa đủ lý do! 😡",
                "Khó ưa vừa đủ để tui lườm bạn từ xa mỗi ngày! 😒",
                "Ghét mà không nói ra, nhưng chắc bạn tự hiểu ha? 😤",
                "Cứ thấy bạn là tui muốn nhấn mute cả thế giới! 😑",
            ]
        )
    elif hate_percentage <= 60:
        return random.choice(
            [
                "Ghét bạn tới mức muốn viết đơn xin nghỉ chơi luôn đó! 😣",
                "Mỗi lần bạn xuất hiện là tui muốn chạy marathon để trốn! 😤",
                "Khó chịu kinh khủng, bạn là lý do tui kiểm tra độ kiên nhẫn! 😡",
                "Ghét kiểu muốn unfollow cả trong giấc mơ luôn á! 😒",
                "Bạn làm tui bực tới mức muốn đổi múi giờ để tránh! 😖",
            ]
        )
    elif hate_percentage <= 80:
        return random.choice(
            [
                "Ghét tới mức tui muốn gửi bạn lên sao Hỏa đơn phương! 😣",
                "Bạn là định nghĩa của khó ưa, tui cạn lời luôn rồi! 😤",
                "Mỗi lần thấy bạn là tui muốn tắt nguồn cả vũ trụ! 😡",
                "Ghét đỉnh cao, chắc kiếp trước tui nợ bạn cái gì nặng lắm! 😒",
                "Tui mà có nút block IRL, bạn đã bay màu từ lâu rồi! 😖",
            ]
        )
    else:
        return random.choice(
            [
                "Ghét tới mức tui muốn chế tạo cỗ máy thời gian để né bạn! 😣",
                "Bạn là cơn ác mộng, tui chỉ muốn wake up khỏi bạn thôi! 😤",
                "Ghét kinh hoàng, chắc tui phải xin đổi hành tinh để sống! 😡",
                "Tui hết chịu nổi, bạn là lý do tui muốn ẩn danh vĩnh viễn! 😒",
                "Ghét tới mức tui muốn viết sử thi về sự khó ưa của bạn! 😖",
            ]
        )

async def process_command(ctx: Message, command_type: str):
    # Phản hồi ngay lập tức khi nhận lệnh
    msg = await ctx.reply_msg(
        f"🔮 Đang đo lường {'sức nóng tình yêu' if command_type == 'love' else 'mức độ ghét'}..."
    )

    try:
        # Lấy thông tin người gửi
        sender_id = ctx.from_user.id
        sender_name = ctx.from_user.first_name
        sender_mention = ctx.from_user.mention
        chat_id = ctx.chat.id

        # Kiểm tra xem người gửi có thể sử dụng lệnh không
        if not await can_use_command(chat_id, sender_id, command_type):
            await msg.edit_msg(
                f"🚫 Bạn đã sử dụng lệnh /{command_type} hôm nay. Hãy thử lại vào ngày mai! 😊"
            )
            return

        # Kiểm tra xem có trả lời tin nhắn hợp lệ không
        target_name = None
        target_mention = None
        if ctx.reply_to_message and ctx.reply_to_message.from_user:
            target_name = ctx.reply_to_message.from_user.first_name
            target_mention = ctx.reply_to_message.from_user.mention
        else:
            # Lấy tên từ tham số lệnh
            command, *args = ctx.text.split(" ", 1)
            if args and args[0].strip():
                target_name = args[0].strip()
                target_mention = target_name  # Non-mention for text input
            else:
                await msg.edit_msg(
                    "Vui lòng nhập một tên sau lệnh hoặc trả lời một tin nhắn! 😊"
                )
                return

        # Tính phần trăm và lấy thông điệp
        percentage = random.randint(0, 100)
        message = (
            get_random_love_message(percentage)
            if command_type == "love"
            else get_random_hate_message(percentage)
        )

        # Tạo caption
        response = (
            f"{'💕' if command_type == 'love' else '⚡'} {sender_mention} + {target_mention} {'💕' if command_type == 'love' else '⚡'}\n"
            f"{'🔥' if command_type == 'love' else '💢'} {'Độ tương hợp' if command_type == 'love' else 'Mức độ ghét'}: {percentage}% {'🔥' if command_type == 'love' else '💢'}\n\n"
            f"{message}"
        )

        # Kiểm tra ảnh trước
        image_path = os.path.join(os.getcwd(), "assets", f"{command_type}.png")
        image_exists = os.path.exists(image_path)

        # Cập nhật dữ liệu sử dụng lệnh cho người gửi
        await update_user_command_usage(chat_id, sender_id, command_type)

        # Gửi phản hồi
        if image_exists:
            await ctx.reply_photo(
                photo=image_path,
                caption=response,
                quote=True
            )
        else:
            await ctx.reply_msg(
                response + f"\n\n⚠️ Không tìm thấy ảnh {command_type}.png trong thư mục assets!",
                quote=True
            )

        await msg.delete()

    except Exception as e:
        logger.error(f"Error in {command_type} command: {str(e)}")
        await msg.edit_msg("Lỗi, vui lòng thử lại sau! 😔")

@app.on_message(
    filters.command("love", COMMAND_HANDLER)
    & ~filters.forwarded
    & ~filters.via_bot
)
@capture_err
async def love_command(_, ctx: Message):
    await process_command(ctx, "love")

@app.on_message(
    filters.command("hate", COMMAND_HANDLER)
    & ~filters.forwarded
    & ~filters.via_bot
)
@capture_err
async def hate_command(_, ctx: Message):
    await process_command(ctx, "hate")