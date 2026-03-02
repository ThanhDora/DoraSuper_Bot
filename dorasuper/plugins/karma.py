import re
import asyncio
import logging
from logging import getLogger
from datetime import datetime
from pyrogram import enums, filters, Client
from pyrogram.errors import PeerIdInvalid
from database.karma_db import (
    get_karma,
    get_karmas,
    is_karma_on,
    karma_off,
    karma_on,
    update_karma,
    reset_all_karma,
)
from dorasuper import app
from dorasuper.emoji import E_ERROR, E_HEART, E_LIST, E_LOADING, E_SUCCESS, E_TIP, E_WARN
from dorasuper.core.decorator.errors import capture_err
from dorasuper.core.decorator.permissions import adminsOnly
from dorasuper.helper.functions import alpha_to_int, int_to_alpha

LOGGER = getLogger("DoraSuper")

__MODULE__ = "TươngTácNhóm"
__HELP__ = """
Dành điểm danh tiếng cho người khác trong nhóm và tự động đánh giá, xếp hạng người dùng dựa trên tương tác. Mặc định BẬT khi bot được thêm vào nhóm.

<blockquote>/fame_toggle [On/Off] - Bật/Tắt hệ thống điểm danh tiếng.
/fame - Xem điểm và vị trí trong bảng xếp hạng, trả lời tin nhắn của người khác để xem của người đó.
/fame_rank - Xem bảng xếp hạng điểm danh tiếng của các thành viên trong nhóm.
/fame_set - Đặt điểm danh tiếng tuỳ chỉnh cho thành viên trong nhóm.
/fame_reset - Đặt lại toàn bộ điểm danh tiếng trong nhóm.</blockquote>
"""

karma_positive_group = 3
karma_negative_group = 4

regex_upvote = r"\b(like|thank you|cảm ơn|thanks|thank|c\.ơn|cám ơn|đội ơn|tks|👍)\b"
regex_downvote = r"\b(không thích|👎|unlike|dislike)\b"

n = "\n"
w = " "

bold = lambda x: f"**{x}:** "
bold_ul = lambda x: f"**--{x}:**-- "
mono = lambda x: f"`{x}`{n}"

def section(
    title: str,
    body: dict,
    indent: int = 2,
    underline: bool = False,
) -> str:
    text = (bold_ul(title) + n) if underline else bold(title) + n

    for key, value in body.items():
        text += (
            indent * w
            + bold(key)
            + ((value[0] + n) if isinstance(value, list) else mono(value))
        )
    return text

async def get_usernames(client, user_ids) -> dict:
    user_dict = {}
    for user_id in user_ids:
        try:
            user = await client.get_users(user_id)
            user_dict[user_id] = user.username if user.username else f"ID: {user_id}"
        except PeerIdInvalid:
            user_dict[user_id] = f"ID: {user_id}"  # Nếu không tìm thấy người dùng, trả về ID
    return user_dict

async def auto_delete_message(message, delay=120):
    await asyncio.sleep(delay)
    await message.delete()

@app.on_message(
    (filters.text | filters.caption)
    & filters.group
    & filters.incoming
    & filters.reply
    & ~filters.via_bot
    & ~filters.bot,
    group=karma_positive_group,
)
@capture_err
async def upvote(_, message):
    text = (message.text or message.caption or "").strip()
    if not text or not re.search(regex_upvote, text, re.IGNORECASE):
        return
    if not await is_karma_on(message.chat.id):
        return
    if not message.reply_to_message.from_user:
        return
    if not message.from_user:
        return
    if message.reply_to_message.from_user.is_bot:
        return
    if message.reply_to_message.from_user.id == message.from_user.id:
        return

    chat_id = message.chat.id
    user_id = message.reply_to_message.from_user.id
    user_mention = message.reply_to_message.from_user.mention

    current_karma = await get_karma(chat_id, await int_to_alpha(user_id))
    if current_karma:
        current_karma = current_karma["karma"]
        karma = current_karma + 10
    else:
        karma = 10

    new_karma = {"karma": karma}
    await update_karma(chat_id, await int_to_alpha(user_id), new_karma)

    response_message = await message.reply_text(
        f"{E_HEART} Bạn làm tốt lắm {user_mention}. Hệ thống đã tăng điểm danh tiếng của bạn vì bạn được người khác khen ngợi hoặc cảm ơn.",
        parse_mode=enums.ParseMode.HTML,
    )

    # Xoá tin nhắn sau 1 phút
    await auto_delete_message(response_message, 120)

@app.on_message(
    (filters.text | filters.caption)
    & filters.group
    & filters.incoming
    & filters.reply
    & ~filters.via_bot
    & ~filters.bot,
    group=karma_negative_group,
)
@capture_err
async def downvote(_, message):
    text = (message.text or message.caption or "").strip()
    if not text or not re.search(regex_downvote, text, re.IGNORECASE):
        return
    if not await is_karma_on(message.chat.id):
        return
    if not message.reply_to_message.from_user:
        return
    if not message.from_user:
        return
    if message.reply_to_message.from_user.is_bot:
        return
    if message.reply_to_message.from_user.id == message.from_user.id:
        return

    chat_id = message.chat.id
    user_id = message.reply_to_message.from_user.id
    user_mention = message.reply_to_message.from_user.mention

    current_karma = await get_karma(chat_id, await int_to_alpha(user_id))
    if current_karma:
        current_karma = current_karma["karma"]
        karma = current_karma - 20
    else:
        karma = -20

    new_karma = {"karma": karma}
    await update_karma(chat_id, await int_to_alpha(user_id), new_karma)

    response_message = await message.reply_text(
        f"😢 Không ổn rồi {user_mention}. Hệ thống đã giảm điểm danh tiếng của bạn xuống vì bạn đã khiến người khác phàn nàn.",
        parse_mode=enums.ParseMode.HTML,
    )

    # Xoá tin nhắn sau 1 phút
    await auto_delete_message(response_message, 120)

@app.on_message(filters.command("fame_rank") & filters.group)
@capture_err
async def command_karma(_, message):
    chat_id = message.chat.id

    m = await message.reply_text(f"{E_LOADING} Đang lấy điểm của toàn bộ thành viên...")

    karma = await get_karmas(chat_id)
    if not karma:
        response_message = await m.edit(
            f"{E_ERROR} Không tìm thấy dữ liệu điểm trong nhóm này. Có vẻ chế độ Fame chưa bật hoặc chưa có tương tác nào giữa người dùng.",
            parse_mode=enums.ParseMode.HTML,
        )
        # Xoá tin nhắn sau 120 giây
        await auto_delete_message(response_message, 120)
        return

    msg_date = datetime.now().strftime("%H:%M %d/%m/%Y")
    karma_text = f"{E_LIST} <b>Top 10 thành viên xếp hạng cao nhất nhóm {message.chat.title} (Cập nhật lúc {msg_date})</b>\n\n\n"

    karma_dicc = {}
    for item in karma:
        user_id = await alpha_to_int(item)
        user_karma = karma[item]["karma"]
        karma_dicc[user_id] = user_karma

    sorted_karma = sorted(karma_dicc.items(), key=lambda x: x[1], reverse=True)

    top_karma_users = sorted_karma[:10]  # Chọn 10 người dùng có điểm cao nhất

    for index, (user_id, karma_count) in enumerate(top_karma_users, start=1):
        try:
            user = await app.get_users(user_id)
            user_mention = user.mention
        except PeerIdInvalid:
            user_mention = "Thành viên"

        karma_text += f"👉 Top {index} là {user_mention} với tổng số điểm là {karma_count} điểm\n\n"

    if not top_karma_users:
        karma_text = "Không tìm thấy điểm trong nhóm này. Có vẻ chế độ Fame chưa bật hoặc chưa có tương tác nào giữa người dùng."

    response_message = await m.edit(karma_text, parse_mode=enums.ParseMode.HTML)
    # Xoá tin nhắn sau 120 giây
    await auto_delete_message(response_message, 120)

@app.on_message(filters.command("fame_reset") & ~filters.private)
@adminsOnly("can_change_info")
async def karma_reset(_, message):
    usage = f"{E_TIP} **Cách sử dụng:**\n/fame_reset"
    if len(message.command) != 1:
        return await message.reply_text(usage)
    
    chat_id = message.chat.id
    
    await reset_all_karma(chat_id)
    
    await message.reply_text(f"{E_SUCCESS} Tất cả điểm danh tiếng đã được đặt lại cho nhóm này.")

@app.on_message(filters.command("fame_toggle") & ~filters.private)
@adminsOnly("can_change_info")
async def fame_toggle(_, message):
    usage = f"{E_TIP} **Cách sử dụng:**\n/fame_toggle [On/Off]"
    if len(message.command) != 2:
        return await message.reply_text(usage)
    
    chat_id = message.chat.id
    state = message.text.split(None, 1)[1].strip().lower()

    if state == "on":
        await karma_on(chat_id)
        await message.reply_text(f"{E_SUCCESS} Hệ thống điểm danh tiếng đã được bật cho nhóm này.")
    elif state == "off":
        await karma_off(chat_id)
        await reset_all_karma(chat_id)
        await message.reply_text(f"{E_SUCCESS} Hệ thống điểm danh tiếng đã được tắt và toàn bộ điểm của thành viên đã được đặt lại.")
    else:
        await message.reply_text(usage)

				
@app.on_message(filters.command("fame_set") & filters.group)
@adminsOnly("can_change_info")
async def set_fame(_, message):
    usage = f"{E_TIP} **Cách sử dụng:**\n/fame_set [số điểm]"
    
    if len(message.command) != 2:
        response_message = await message.reply_text(usage)
        await auto_delete_message(response_message, 120)
        return
    
    if not message.reply_to_message or not message.reply_to_message.from_user:
        response_message = await message.reply_text(f"{E_TIP} Hãy reply vào tin nhắn của thành viên bạn muốn đặt điểm.")
        await auto_delete_message(response_message, 120)
        return

    try:
        points = int(message.command[1])
    except ValueError:
        response_message = await message.reply_text(f"{E_WARN} Số điểm phải là một số nguyên.")
        await auto_delete_message(response_message, 120)
        return
    
    user_id = message.reply_to_message.from_user.id
    chat_id = message.chat.id
    
    current_karma = await get_karma(chat_id, await int_to_alpha(user_id))
    if current_karma:
        karma = points
    else:
        karma = points
    
    new_karma = {"karma": karma}
    await update_karma(chat_id, await int_to_alpha(user_id), new_karma)
    
    response_message = await message.reply_text(f"{E_SUCCESS} Điểm danh tiếng của thành viên đã được đặt thành {karma} điểm.")
    await auto_delete_message(response_message, 120)
		
@app.on_message(filters.command("fame") & filters.group)
@capture_err
async def fame(_, message):
    chat_id = message.chat.id

    # Kiểm tra nếu không có from_user (tức là người dùng tương tác dưới tư cách kênh)
    if message.from_user is None:
        response_message = await message.reply_text(f"{E_WARN} Người dùng tương tác bằng kênh sẽ không thể sử dụng hệ thống chấm điểm thành viên.")
        await auto_delete_message(response_message, 120)
        return

    # Kiểm tra xem lệnh có được reply vào tin nhắn không
    if message.reply_to_message:
        if message.reply_to_message.sender_chat:
            # Nếu reply vào tin nhắn từ kênh
            response_message = await message.reply_text(f"{E_WARN} Người dùng tương tác bằng kênh sẽ không thể sử dụng hệ thống chấm điểm thành viên.")
            await auto_delete_message(response_message, 120)
            return
        elif message.reply_to_message.from_user:
            # Nếu reply vào tin nhắn từ người dùng cá nhân
            user_id = message.reply_to_message.from_user.id
            user_mention = message.reply_to_message.from_user.mention
    else:
        # Nếu không reply, lấy ID của người gửi lệnh
        user_id = message.from_user.id
        user_mention = message.from_user.mention

    # Kiểm tra nếu user_id là bot, không trả lời
    if message.reply_to_message and message.reply_to_message.from_user.is_bot:
        return  # Không thông báo nếu tìm điểm của bot

    karma = await get_karmas(chat_id)
    if not karma:
        response_message = await message.reply_text(f"{E_LIST} Không tìm thấy dữ liệu điểm trong nhóm này. Chế độ Fame chưa bật hoặc chưa có tương tác nào.")
        await auto_delete_message(response_message, 120)
        return

    karma_dicc = {}
    for item in karma:
        uid = await alpha_to_int(item)
        user_karma = karma[item]["karma"]
        karma_dicc[uid] = user_karma

    sorted_karma = sorted(karma_dicc.items(), key=lambda x: x[1], reverse=True)

    for rank, (uid, karma_count) in enumerate(sorted_karma, start=1):
        if uid == user_id:
            response_message = await message.reply_text(f"{E_HEART} {user_mention} đang ở vị trí thứ {rank} trong bảng xếp hạng với {karma_count} điểm.")
            await auto_delete_message(response_message, 120)
            return
    
    response_message = await message.reply_text(f"{E_HEART} {user_mention} chưa có điểm trong bảng xếp hạng. Hãy tương tác với thành viên trong nhóm để kiếm điểm!")
    await auto_delete_message(response_message, 120)