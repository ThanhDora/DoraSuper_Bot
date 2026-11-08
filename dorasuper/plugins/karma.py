import asyncio
import html
from datetime import datetime

from pyrogram import enums, filters
from pyrogram.errors import MessageIdInvalid, PeerIdInvalid
from pyrogram.types import Message

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
from dorasuper.emoji import (
    E_CLOCK, E_ERROR, E_FIRE, E_GROUP, E_HEART, E_LIST, E_LOADING, E_MEDAL,
    E_ONE, E_SPARKLE, E_STAR, E_SUCCESS, E_THREE, E_TIP, E_TROPHY, E_TWO, E_WARN,
)
from dorasuper.core.decorator.errors import capture_err
from dorasuper.core.decorator.permissions import adminsOnly
from dorasuper.helper.fame import is_downvote, is_upvote, mention_user
from dorasuper.helper.functions import alpha_to_int, int_to_alpha
from dorasuper.vars import COMMAND_HANDLER

__MODULE__ = "TươngTácNhóm"
__HELP__ = f"""
Dành điểm danh tiếng cho người khác trong nhóm và xếp hạng thành viên dựa trên lời khen hoặc phàn nàn. Mặc định <b>bật</b> khi bot ở trong nhóm.

<blockquote>Cách cộng điểm: trả lời tin nhắn của người khác bằng cảm ơn, thanks, tks, like, 👍, +, ++, +1
hoặc dùng lệnh <code>/thanks</code> (trả lời tin nhắn đó).

Cách trừ điểm: trả lời bằng không thích, unlike, dislike, 👎, -, --, -1
hoặc dùng lệnh <code>/unlike</code>.

/fame – Xem điểm và thứ hạng của mình, hoặc trả lời tin nhắn để xem của người đó.
/fame_rank – Xem top 10 thành viên có điểm cao nhất nhóm.
/fame_toggle [On/Off] – Bật/tắt hệ thống điểm danh tiếng.
/fame_set [số điểm] – Đặt điểm cho thành viên (trả lời tin nhắn của họ).
/fame_reset – Đặt lại toàn bộ điểm trong nhóm.</blockquote>
"""

karma_positive_group = 3
karma_negative_group = 4

_GROUP_ONLY = f"{E_WARN} Lệnh này chỉ dùng được trong nhóm. Anh/chị hãy gửi trong nhóm có bot nhé."
_FAME_PM_COMMANDS = [
    "fame", "fame_rank", "fame_reset", "fame_toggle", "fame_set",
    "thanks", "thank", "tks", "like", "unlike", "dislike",
]

def _rank_badge(index: int) -> str:
    if index == 1:
        return f"{E_ONE} {E_TROPHY}"
    if index == 2:
        return f"{E_TWO} {E_MEDAL}"
    if index == 3:
        return f"{E_THREE} {E_STAR}"
    return f"{E_FIRE} <b>{index}.</b>"


async def auto_delete_message(message, delay=120):
    await asyncio.sleep(delay)
    await message.delete()


async def _reply_html(message: Message, text: str, **kwargs):
    kwargs.setdefault("parse_mode", enums.ParseMode.HTML)
    try:
        return await message.reply_text(text, **kwargs)
    except MessageIdInvalid:
        if getattr(message, "message_thread_id", None):
            kwargs.setdefault("message_thread_id", message.message_thread_id)
        return await app.send_message(message.chat.id, text, **kwargs)


async def _apply_vote(message: Message, delta: int, template: str):
    if not await is_karma_on(message.chat.id):
        return
    reply = message.reply_to_message
    if not reply or not reply.from_user or not message.from_user:
        return
    if reply.from_user.is_bot:
        return
    if reply.from_user.id == message.from_user.id:
        return

    chat_id = message.chat.id
    user_id = reply.from_user.id
    user_mention = mention_user(reply.from_user)

    current_karma = await get_karma(chat_id, await int_to_alpha(user_id))
    karma = (current_karma["karma"] + delta) if current_karma else delta

    await update_karma(chat_id, await int_to_alpha(user_id), {"karma": karma})
    response_message = await _reply_html(message, template.format(mention=user_mention))
    await auto_delete_message(response_message, 120)


@app.on_message(filters.command(_FAME_PM_COMMANDS, COMMAND_HANDLER) & filters.private, group=-1)
@capture_err
async def fame_private(_, message: Message):
    await _reply_html(message, _GROUP_ONLY)


@app.on_message(
    (filters.text | filters.caption)
    & filters.group
    & filters.incoming
    & filters.reply
    & ~filters.via_bot
    & ~filters.bot
    & ~filters.command(_FAME_PM_COMMANDS, COMMAND_HANDLER),
    group=karma_positive_group,
)
@capture_err
async def upvote(_, message):
    text = (message.text or message.caption or "").strip()
    if not is_upvote(text):
        return
    await _apply_vote(
        message,
        10,
        f"{E_HEART} Bạn làm tốt lắm {{mention}}. Hệ thống đã tăng điểm danh tiếng của bạn vì bạn được người khác khen ngợi hoặc cảm ơn.",
    )


@app.on_message(
    (filters.text | filters.caption)
    & filters.group
    & filters.incoming
    & filters.reply
    & ~filters.via_bot
    & ~filters.bot
    & ~filters.command(_FAME_PM_COMMANDS, COMMAND_HANDLER),
    group=karma_negative_group,
)
@capture_err
async def downvote(_, message):
    text = (message.text or message.caption or "").strip()
    if not is_downvote(text):
        return
    await _apply_vote(
        message,
        -20,
        f"😢 Không ổn rồi {{mention}}. Hệ thống đã giảm điểm danh tiếng của bạn xuống vì bạn đã khiến người khác phàn nàn.",
    )


@app.on_message(
    filters.command(["thanks", "thank", "tks", "like"], COMMAND_HANDLER)
    & ~filters.private
    & filters.incoming
    & ~filters.via_bot
    & ~filters.bot,
    group=-1,
)
@capture_err
async def thanks_cmd(_, message: Message):
    if not message.reply_to_message or not getattr(message.reply_to_message, "from_user", None):
        response = await _reply_html(
            message,
            f"{E_TIP} Hãy trả lời tin nhắn của người anh/chị muốn cộng điểm, rồi gửi <code>/thanks</code>.",
        )
        await auto_delete_message(response, 120)
        return
    await _apply_vote(
        message,
        10,
        f"{E_HEART} Bạn làm tốt lắm {{mention}}. Hệ thống đã tăng điểm danh tiếng của bạn vì bạn được người khác khen ngợi hoặc cảm ơn.",
    )


@app.on_message(
    filters.command(["unlike", "dislike"], COMMAND_HANDLER)
    & ~filters.private
    & filters.incoming
    & ~filters.via_bot
    & ~filters.bot,
    group=-1,
)
@capture_err
async def unlike_cmd(_, message: Message):
    if not message.reply_to_message or not getattr(message.reply_to_message, "from_user", None):
        response = await _reply_html(
            message,
            f"{E_TIP} Hãy trả lời tin nhắn của người anh/chị muốn trừ điểm, rồi gửi <code>/unlike</code>.",
        )
        await auto_delete_message(response, 120)
        return
    await _apply_vote(
        message,
        -20,
        f"😢 Không ổn rồi {{mention}}. Hệ thống đã giảm điểm danh tiếng của bạn xuống vì bạn đã khiến người khác phàn nàn.",
    )


@app.on_message(filters.command("fame_rank", COMMAND_HANDLER) & ~filters.private, group=-1)
@capture_err
async def command_karma(_, message):
    chat_id = message.chat.id

    m = await _reply_html(message, f"{E_LOADING} Đang lấy điểm của toàn bộ thành viên...")

    karma = await get_karmas(chat_id)
    if not karma:
        response_message = await m.edit(
            f"{E_ERROR} Không tìm thấy dữ liệu điểm trong nhóm này. Có vẻ chế độ Fame chưa bật hoặc chưa có tương tác nào giữa người dùng.",
            parse_mode=enums.ParseMode.HTML,
        )
        await auto_delete_message(response_message, 120)
        return

    msg_date = datetime.now().strftime("%H:%M %d/%m/%Y")
    title = html.escape(message.chat.title or "nhóm")
    karma_text = (
        f"{E_TROPHY}{E_SPARKLE} <b>Top 10 thành viên xếp hạng cao nhất</b>\n"
        f"{E_GROUP} Nhóm: <b>{title}</b>\n"
        f"{E_CLOCK} Cập nhật lúc {msg_date}\n\n"
    )

    karma_dicc = {}
    for item in karma:
        user_id = await alpha_to_int(item)
        user_karma = karma[item]["karma"]
        karma_dicc[user_id] = user_karma

    sorted_karma = sorted(karma_dicc.items(), key=lambda x: x[1], reverse=True)
    top_karma_users = sorted_karma[:10]

    for index, (user_id, karma_count) in enumerate(top_karma_users, start=1):
        try:
            user = await app.get_users(user_id)
            user_mention = mention_user(user)
        except PeerIdInvalid:
            user_mention = "Thành viên"

        karma_text += f"{_rank_badge(index)} {user_mention} — {E_STAR} <code>{karma_count}</code> điểm\n"

    if not top_karma_users:
        karma_text = "Không tìm thấy điểm trong nhóm này. Có vẻ chế độ Fame chưa bật hoặc chưa có tương tác nào giữa người dùng."

    response_message = await m.edit(karma_text, parse_mode=enums.ParseMode.HTML)
    await auto_delete_message(response_message, 120)


@app.on_message(filters.command("fame_reset", COMMAND_HANDLER) & ~filters.private, group=-1)
@adminsOnly("can_change_info")
async def karma_reset(_, message):
    usage = f"{E_TIP} <b>Cách sử dụng:</b>\n<code>/fame_reset</code>"
    if len(message.command) != 1:
        return await _reply_html(message, usage)

    chat_id = message.chat.id
    await reset_all_karma(chat_id)
    await _reply_html(message, f"{E_SUCCESS} Tất cả điểm danh tiếng đã được đặt lại cho nhóm này.")


@app.on_message(filters.command("fame_toggle", COMMAND_HANDLER) & ~filters.private, group=-1)
@adminsOnly("can_change_info")
async def fame_toggle(_, message):
    usage = f"{E_TIP} <b>Cách sử dụng:</b>\n<code>/fame_toggle [On/Off]</code>"
    if len(message.command) != 2:
        return await _reply_html(message, usage)

    chat_id = message.chat.id
    state = message.text.split(None, 1)[1].strip().lower()

    if state == "on":
        await karma_on(chat_id)
        await _reply_html(message, f"{E_SUCCESS} Hệ thống điểm danh tiếng đã được bật cho nhóm này.")
    elif state == "off":
        await karma_off(chat_id)
        await reset_all_karma(chat_id)
        await _reply_html(message, f"{E_SUCCESS} Hệ thống điểm danh tiếng đã được tắt và toàn bộ điểm của thành viên đã được đặt lại.")
    else:
        await _reply_html(message, usage)


@app.on_message(filters.command("fame_set", COMMAND_HANDLER) & ~filters.private, group=-1)
@adminsOnly("can_change_info")
async def set_fame(_, message):
    usage = f"{E_TIP} <b>Cách sử dụng:</b>\n<code>/fame_set [số điểm]</code>"

    if len(message.command) != 2:
        response_message = await _reply_html(message, usage)
        await auto_delete_message(response_message, 120)
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        response_message = await _reply_html(
            message, f"{E_TIP} Hãy reply vào tin nhắn của thành viên bạn muốn đặt điểm."
        )
        await auto_delete_message(response_message, 120)
        return

    try:
        points = int(message.command[1])
    except ValueError:
        response_message = await _reply_html(message, f"{E_WARN} Số điểm phải là một số nguyên.")
        await auto_delete_message(response_message, 120)
        return

    user_id = message.reply_to_message.from_user.id
    chat_id = message.chat.id
    await update_karma(chat_id, await int_to_alpha(user_id), {"karma": points})

    response_message = await _reply_html(
        message,
        f"{E_SUCCESS} Điểm danh tiếng của thành viên đã được đặt thành {points} điểm.",
    )
    await auto_delete_message(response_message, 120)


@app.on_message(filters.command("fame", COMMAND_HANDLER) & ~filters.private, group=-1)
@capture_err
async def fame(_, message):
    chat_id = message.chat.id

    if message.from_user is None:
        response_message = await _reply_html(
            message,
            f"{E_WARN} Người dùng tương tác bằng kênh sẽ không thể sử dụng hệ thống chấm điểm thành viên.",
        )
        await auto_delete_message(response_message, 120)
        return

    if message.reply_to_message:
        if message.reply_to_message.sender_chat:
            response_message = await _reply_html(
                message,
                f"{E_WARN} Người dùng tương tác bằng kênh sẽ không thể sử dụng hệ thống chấm điểm thành viên.",
            )
            await auto_delete_message(response_message, 120)
            return
        if not message.reply_to_message.from_user:
            response_message = await _reply_html(
                message,
                f"{E_WARN} Không xác định được thành viên để xem điểm.",
            )
            await auto_delete_message(response_message, 120)
            return
        if message.reply_to_message.from_user.is_bot:
            return
        user_id = message.reply_to_message.from_user.id
        user_mention = mention_user(message.reply_to_message.from_user)
    else:
        user_id = message.from_user.id
        user_mention = mention_user(message.from_user)

    karma = await get_karmas(chat_id)
    if not karma:
        response_message = await _reply_html(
            message,
            f"{E_LIST} Không tìm thấy dữ liệu điểm trong nhóm này. Chế độ Fame chưa bật hoặc chưa có tương tác nào.",
        )
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
            response_message = await _reply_html(
                message,
                f"{E_HEART} {user_mention} đang ở vị trí thứ {rank} trong bảng xếp hạng với {karma_count} điểm.",
            )
            await auto_delete_message(response_message, 120)
            return

    response_message = await _reply_html(
        message,
        f"{E_HEART} {user_mention} chưa có điểm trong bảng xếp hạng. Hãy tương tác với thành viên trong nhóm để kiếm điểm!",
    )
    await auto_delete_message(response_message, 120)
