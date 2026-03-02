import html
import os
import random
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message

from database.funny_db import can_use_command, update_user_command_usage
from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.emoji import (
    E_CLOCK,
    E_CROSS,
    E_DIAMON,
    E_ERROR,
    E_EYE_ROLL,
    E_FIRE,
    E_FLOWER,
    E_GLARE,
    E_GRASS,
    E_HEART,
    E_HEART2,
    E_HEART3,
    E_HEART4,
    E_ICE,
    E_LIMIT,
    E_LOADING,
    E_NOTE,
    E_PARTY,
    E_SHOUT,
    E_SPARKLE,
    E_STAR,
    E_SWEET,
    E_TIP,
    E_TROPHY,
    E_UNCOMFORTABLE,
    E_WARN,
)
from dorasuper.vars import COMMAND_HANDLER

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
                f"{E_SPARKLE} Tình yêu còn mờ nhạt, cần thêm chút phép màu để tỏa sáng!",
                f"{E_FIRE} Chỉ là một tia sáng nhỏ, hãy thổi bùng ngọn lửa tình đi nào!",
                f"{E_HEART} Hơi lạnh nhạt, nhưng mọi chuyện tình đều bắt đầu từ đây! {E_ICE}",
                f"{E_SPARKLE} Tình cảm mới nhen nhóm, hãy kiên nhẫn nhé! {E_GRASS}",
                f"{E_STAR} Chút rung động ban đầu, nhưng tương lai còn nhiều bất ngờ! {E_SPARKLE}",
            ]
        )
    elif love_percentage <= 40:
        return random.choice(
            [
                f"{E_HEART} Tình yêu đang lấp ló, hãy mở lòng để nó nở hoa! {E_FLOWER}",
                f"{E_HEART2} Có chút gì đó ngọt ngào, nhưng cần thêm thời gian để chín muồi! {E_SWEET}",
                f"{E_FIRE} Trái tim bắt đầu rung rinh, cứ tiếp tục là sẽ bùng nổ! {E_HEART2}",
                f"{E_STAR} Một khởi đầu đầy hứa hẹn, hãy cùng viết câu chuyện tình! {E_NOTE}",
                f"{E_HEART} Tình cảm đang lớn dần, chỉ cần chút chăm sóc là đủ! {E_FLOWER}",
            ]
        )
    elif love_percentage <= 60:
        return random.choice(
            [
                f"{E_FIRE} Tình yêu đang ấm lên, hãy giữ lửa để nó cháy mãi!",
                f"{E_HEART2} Hai trái tim đang hòa nhịp, cứ thế này là ngọt ngào lắm! {E_HEART3}",
                f"{E_STAR} Kết nối khá mạnh, chỉ cần chút gia vị để hoàn hảo! {E_STAR}",
                f"{E_HEART} Tình cảm đang nở rộ, hãy cùng nhau làm nó thêm đặc biệt! {E_FLOWER}",
                f"{E_SPARKLE} Cảm xúc dâng trào, chuyện tình này sắp thành cổ tích rồi! {E_PARTY}",
            ]
        )
    elif love_percentage <= 80:
        return random.choice(
            [
                f"{E_HEART2} Wow, tình yêu mãnh liệt, hai bạn sinh ra để dành cho nhau! {E_HEART4}",
                f"{E_HEART} Trái tim hòa quyện, chuyện tình này đẹp như một bài thơ! {E_NOTE}",
                f"{E_FIRE} Tình yêu bùng cháy, hãy giữ để nó mãi rực rỡ nhé!",
                f"{E_STAR} Cặp đôi hoàn hảo, chỉ cần nhìn là biết định mệnh! {E_FLOWER}",
                f"{E_HEART2} Hạnh phúc ngập tràn, tình yêu này đáng để trân trọng! {E_TROPHY}",
            ]
        )
    else:
        return random.choice(
            [
                f"{E_STAR} Trời ơi, tình yêu đỉnh cao, hai bạn là cặp đôi huyền thoại! {E_DIAMON}",
                f"{E_HEART2} Tình yêu vĩnh cửu, không gì có thể chia cắt hai bạn! {E_HEART3}",
                f"{E_HEART} Định mệnh an bài, hai trái tim này sinh ra để thuộc về nhau! {E_GRASS}",
                f"{E_SPARKLE} Hoàn hảo tuyệt đối, chuyện tình này làm cả thế giới ghen tị! {E_HEART}",
                f"{E_FIRE} Tình yêu vượt thời gian, mãi mãi là của nhau! {E_CLOCK}",
            ]
        )

def get_random_hate_message(hate_percentage):
    if hate_percentage <= 20:
        return random.choice(
            [
                f"{E_WARN} Hơi khó chịu thôi, nhưng chắc tui lờ đi được... tạm thời! {E_GLARE}",
                f"{E_CROSS} Nhìn là muốn tránh xa, mà sao cứ lởn vởn trước mặt thế? {E_UNCOMFORTABLE}",
                f"{E_WARN} Ghét nhẹ nhẹ, kiểu như thấy bạn là mắt tui tự lườm! {E_EYE_ROLL}",
                f"{E_CROSS} Chỉ muốn nói 'tránh xa tui ra', nhưng thôi, để lần sau! {E_SHOUT}",
                f"{E_WARN} Hơi bực mình, nhưng tui kiềm chế được... lần này thôi nhé! {E_UNCOMFORTABLE}",
            ]
        )
    elif hate_percentage <= 40:
        return random.choice(
            [
                f"{E_CROSS} Ghét vừa vừa, nhưng mỗi lần thấy bạn là tui muốn đổi tần số sống! {E_UNCOMFORTABLE}",
                f"{E_WARN} Bạn làm tui ngứa mắt ghê, kiểu muốn block mà chưa đủ lý do! {E_SHOUT}",
                f"{E_CROSS} Khó ưa vừa đủ để tui lườm bạn từ xa mỗi ngày! {E_GLARE}",
                f"{E_WARN} Ghét mà không nói ra, nhưng chắc bạn tự hiểu ha? {E_SHOUT}",
                f"{E_CROSS} Cứ thấy bạn là tui muốn nhấn mute cả thế giới! {E_EYE_ROLL}",
            ]
        )
    elif hate_percentage <= 60:
        return random.choice(
            [
                f"{E_WARN} Ghét bạn tới mức muốn viết đơn xin nghỉ chơi luôn đó! {E_UNCOMFORTABLE}",
                f"{E_CROSS} Mỗi lần bạn xuất hiện là tui muốn chạy marathon để trốn! {E_SHOUT}",
                f"{E_WARN} Khó chịu kinh khủng, bạn là lý do tui kiểm tra độ kiên nhẫn! {E_SHOUT}",
                f"{E_CROSS} Ghét kiểu muốn unfollow cả trong giấc mơ luôn á! {E_GLARE}",
                f"{E_WARN} Bạn làm tui bực tới mức muốn đổi múi giờ để tránh! {E_UNCOMFORTABLE}",
            ]
        )
    elif hate_percentage <= 80:
        return random.choice(
            [
                f"{E_CROSS} Ghét tới mức tui muốn gửi bạn lên sao Hỏa đơn phương! {E_UNCOMFORTABLE}",
                f"{E_WARN} Bạn là định nghĩa của khó ưa, tui cạn lời luôn rồi! {E_SHOUT}",
                f"{E_CROSS} Mỗi lần thấy bạn là tui muốn tắt nguồn cả vũ trụ! {E_SHOUT}",
                f"{E_WARN} Ghét đỉnh cao, chắc kiếp trước tui nợ bạn cái gì nặng lắm! {E_GLARE}",
                f"{E_CROSS} Tui mà có nút block IRL, bạn đã bay màu từ lâu rồi! {E_UNCOMFORTABLE}",
            ]
        )
    else:
        return random.choice(
            [
                f"{E_WARN} Ghét tới mức tui muốn chế tạo cỗ máy thời gian để né bạn! {E_UNCOMFORTABLE}",
                f"{E_CROSS} Bạn là cơn ác mộng, tui chỉ muốn wake up khỏi bạn thôi! {E_SHOUT}",
                f"{E_WARN} Ghét kinh hoàng, chắc tui phải xin đổi hành tinh để sống! {E_SHOUT}",
                f"{E_CROSS} Tui hết chịu nổi, bạn là lý do tui muốn ẩn danh vĩnh viễn! {E_GLARE}",
                f"{E_WARN} Ghét tới mức tui muốn viết sử thi về sự khó ưa của bạn! {E_UNCOMFORTABLE}",
            ]
        )

async def process_command(ctx: Message, command_type: str):
    rid = ctx.id
    # Phản hồi ngay lập tức khi nhận lệnh (để user thấy bot đã nhận)
    msg = await ctx.reply_msg(
        f"{E_LOADING} Đang đo lường {'sức nóng tình yêu' if command_type == 'love' else 'mức độ ghét'}...",
        parse_mode=enums.ParseMode.HTML,
        reply_to_message_id=rid,
    )

    try:
        if not ctx.from_user:
            await msg.edit_msg(
                f"{E_WARN} Không xác định được người gửi (ví dụ: gửi khi ẩn danh). Hãy tắt ẩn danh hoặc gửi lại.",
                parse_mode=enums.ParseMode.HTML,
            )
            return
        # Lấy thông tin người gửi (mention an toàn cho HTML)
        u = ctx.from_user
        sender_id = u.id
        sender_name = u.first_name or ""
        sender_mention = f'<a href="tg://user?id={sender_id}">{html.escape(sender_name)}</a>'
        chat_id = ctx.chat.id

        # Kiểm tra xem người gửi có thể sử dụng lệnh không
        if not await can_use_command(chat_id, sender_id, command_type):
            await msg.edit_msg(
                f"{E_LIMIT} Bạn đã sử dụng lệnh /{command_type} hôm nay. Hãy thử lại vào ngày mai!",
                parse_mode=enums.ParseMode.HTML,
            )
            return

        # Kiểm tra xem có trả lời tin nhắn hợp lệ không
        target_name = None
        target_mention = None
        if ctx.reply_to_message:
            if ctx.reply_to_message.from_user:
                u = ctx.reply_to_message.from_user
                target_name = u.first_name or ""
                target_mention = f'<a href="tg://user?id={u.id}">{html.escape(target_name)}</a>'
            else:
                await msg.edit_msg(
                    f"{E_TIP} Không lấy được người từ tin bạn reply (tin từ kênh hoặc ẩn danh?). Hãy gõ tên sau lệnh, ví dụ: /{command_type} Tên_người",
                    parse_mode=enums.ParseMode.HTML,
                )
                return
        if target_mention is None:
            # Lấy tên từ tham số lệnh (escape để tránh ENTITY_TEXT_INVALID với ParseMode.HTML)
            command, *args = (ctx.text or "").strip().split(" ", 1)
            if args and args[0].strip():
                target_name = args[0].strip()
                target_mention = html.escape(target_name)
            else:
                await msg.edit_msg(
                    f"{E_TIP} Vui lòng nhập một tên sau lệnh hoặc trả lời tin nhắn của thành viên!",
                    parse_mode=enums.ParseMode.HTML,
                )
                return

        # Tính phần trăm và lấy thông điệp
        percentage = random.randint(0, 100)
        message = (
            get_random_love_message(percentage)
            if command_type == "love"
            else get_random_hate_message(percentage)
        )

        # Tạo caption (dùng emoji custom cho phần header)
        if command_type == "love":
            header = f"{E_HEART} {sender_mention} + {target_mention} {E_HEART2}"
            sub = f"{E_FIRE} Độ tương hợp: {percentage}% {E_FIRE}"
        else:
            header = f"{E_FIRE} {sender_mention} + {target_mention} {E_FIRE}"
            sub = f"{E_SHOUT} Mức độ ghét: {percentage}% {E_SHOUT}"
        response = f"{header}\n{sub}\n\n{message}"

        # Kiểm tra ảnh trước
        image_path = os.path.join(os.getcwd(), "assets", f"{command_type}.png")
        image_exists = os.path.exists(image_path)

        # Cập nhật dữ liệu sử dụng lệnh cho người gửi
        await update_user_command_usage(chat_id, sender_id, command_type)

        # Gửi phản hồi (reply đúng tin lệnh)
        if image_exists:
            await ctx.reply_photo(
                photo=image_path,
                caption=response,
                reply_to_message_id=rid,
                parse_mode=enums.ParseMode.HTML,
            )
        else:
            await ctx.reply_msg(
                response + f"\n\n{E_WARN} Không tìm thấy ảnh {command_type}.png trong thư mục assets!",
                reply_to_message_id=rid,
                parse_mode=enums.ParseMode.HTML,
            )

        await msg.delete()

    except Exception as e:
        LOGGER.error("Error in %s command: %s", command_type, e)
        await msg.edit_msg(
            f"{E_ERROR} Lỗi, vui lòng thử lại sau!",
            parse_mode=enums.ParseMode.HTML,
        )

@app.on_message(
    filters.command("love", COMMAND_HANDLER)
    & ~filters.forwarded
    & ~filters.via_bot,
    group=2,
)
@capture_err
async def love_command(_, ctx: Message):
    await process_command(ctx, "love")

@app.on_message(
    filters.command("hate", COMMAND_HANDLER)
    & ~filters.forwarded
    & ~filters.via_bot,
    group=2,
)
@capture_err
async def hate_command(_, ctx: Message):
    await process_command(ctx, "hate")