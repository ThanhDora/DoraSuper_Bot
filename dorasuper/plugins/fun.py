import html
import re
import textwrap
import unicodedata
from asyncio import gather
from datetime import datetime, timedelta
import asyncio
import logging
import os
import random
import regex
import uuid
import tempfile
from logging import getLogger
from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import MessageIdInvalid, PeerIdInvalid, ReactionInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatPermissions
from dorasuper import app, user, BOT_USERNAME
from dorasuper.emoji import (
    E_NOTE, E_SEARCH, E_WARN, E_BOT, E_PARTY, E_WAIT, E_MSG, E_VUAM,
    E_QUESTION, E_STAR, E_BELL, E_MEGAPHONE, E_HEART, E_MUSIC, E_FIRE,
    E_GLOBE, E_SOS, E_SHIELD, E_PIN_LOC, E_SPARKLE, E_ROCKET, E_HEART3,
    E_THUNDER, E_MENU, E_COFFEE, E_SUCCESS, E_LOCK, E_LOADING, E_PENDING,
    E_TYMMY, E_BITE_YOUR_LIPS, E_WINK, E_SIDEWAYS,
)
from dorasuper.core.decorator.errors import capture_err
from dorasuper.core.decorator.permissions import member_permissions, list_admins
from dorasuper.helper.emoji_fmt import EMOJI_FMT
from dorasuper.helper.localization import use_chat_lang
from dorasuper.vars import COMMAND_HANDLER, ROOT_DIR, SUDO
from database.chat_ban_db import add_chat_ban, remove_chat_ban
from database.chat_mute_db import add_chat_mute, remove_chat_mute

LOGGER = getLogger(__name__)

__MODULE__ = "🎮 Fun & Game"
__HELP__ = """
<blockquote>🎲 <b>Fun & Game</b>

/xucxac, /tungxx – Tung xúc xắc (dice)
/tungxu [sấp|ngửa] – Tung đồng xu, đoán sấp hoặc ngửa

👤 /anony [tin nhắn] – Gửi tin nhắn nặc danh (reply tin người nhận)
💬 <b>Dùng từ khoá (không cần lệnh):</b> reply tin người cần xử lý rồi gõ <b>khoá mõm</b> / <b>đá</b> / <b>cấm</b>. Nếu bot không trả lời thì gõ <b>@TênBot khoá mõm</b> (vẫn reply vào người đó) hoặc tắt Group Privacy: BotFather → Bot Settings → Group Privacy → Turn Off.
🔇 /khoamom – Reply + lệnh (luôn nhận được).</blockquote>
"""


@app.on_message(filters.command(["xucxac", "tungxx", "dice"], COMMAND_HANDLER))
@use_chat_lang()
async def dice(c, m, strings):
    dices = await c.send_dice(m.chat.id, reply_to_message_id=m.id)
    await dices.reply_msg(strings("result").format(number=dices.dice.value, **EMOJI_FMT), quote=True)


@app.on_message(filters.command(["anony", "anon"], COMMAND_HANDLER))
async def beriharapan(c, m):
    reply = m.reply_to_message

    if not reply:
        return await m.reply(f"{E_MSG} Hãy trả lời một tin nhắn để thực hiện lệnh này.")

    if len(m.text.split(maxsplit=1)) < 2:
        return await m.reply(f"{E_WARN} Hãy nhập tin nhắn sau lệnh /anony.")

    pesan = m.text.split(maxsplit=1)[1]
    if reply.from_user:
        reply_name = reply.from_user.mention
    elif reply.sender_chat:
        reply_name = reply.sender_chat.title
    else:
        return await m.reply(f"{E_WARN} Không thể xác định người nhận.")

    await reply.reply(f"{pesan}\n\n{E_MSG} Được ai đó gửi tới {reply_name}", parse_mode=ParseMode.HTML)


@app.on_message(filters.command("react", COMMAND_HANDLER) & filters.user(SUDO))
@user.on_message(filters.command("react", "."))
async def givereact(c, m):
    if len(m.command) == 1:
        return await m.reply(
            "Vui lòng thêm phản ứng sau lệnh, bạn cũng có thể đưa ra nhiều phản ứng."
        )
    if not m.reply_to_message:
        return await m.reply("Vui lòng trả lời tin nhắn bạn muốn phản hồi.")
    emot = list(regex.findall(r"\p{Emoji}", m.text))
    if not emot:
        return await m.reply(f"{E_WARN} Vui lòng thêm ít nhất một emoji sau lệnh.")
    try:
        await m.reply_to_message.react(emoji=emot[0])
    except ReactionInvalid:
        await m.reply("Hãy đưa ra phản ứng chính xác.")
    except MessageIdInvalid:
        await m.reply(
            "Xin lỗi, tôi không thể phản ứng với các bot khác hoặc không có tư cách quản trị viên."
        )
    except PeerIdInvalid:
        await m.reply("Xin lỗi, tôi không thể phản hồi trò chuyện nếu không tham gia nhóm đó.")
    except Exception as err:
        await m.reply(str(err))


# @app.on_message_reaction_updated(filters.chat(-1001777794636))
async def reaction_update(self, ctx):
    self.log.info(ctx)

# Đường dẫn tới file GIF (tương đối thư mục dự án)
GIF_PATH = str(ROOT_DIR / "assets" / "tungxu.gif")

# Hàm xử lý khi người dùng gõ lệnh /coin
@app.on_message(filters.command("tungxu", COMMAND_HANDLER))
async def coin_flip_command(client, message):
    user_id = message.from_user.id
    
    # Kiểm tra nội dung sau lệnh /coin
    try:
        user_input = message.text.split(maxsplit=1)[1].lower()  # Lấy phần nội dung sau /coin
    except IndexError:
        await message.reply(f"{E_WARN} Bạn phải nhập 'sấp' hoặc 'ngửa' sau lệnh /tungxu. Ví dụ: /tungxu sấp")
        return

    # Kiểm tra xem có chứa "sấp" hoặc "ngửa"
    if "sấp" not in user_input and "ngửa" not in user_input:
        await message.reply(f"{E_WARN} Sai cú pháp! Bạn phải nhập 'sấp' hoặc 'ngửa'. Ví dụ: /tungxu tôi đoán sấp")
        return

    # Xác định dự đoán
    guess = "sấp" if "sấp" in user_input else "ngửa"

    # Tạo nút "Tung luôn" và đính kèm ID người dùng
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Tung luôn", callback_data=f"flip:{user_id}")]
        ]
    )
    reply_message = await message.reply(f"{E_PARTY} Bạn đã đoán là xu sẽ <b>{guess}</b>. Nhấn nút bên dưới để tung đồng xu!", reply_markup=buttons, parse_mode=ParseMode.HTML)

# Hàm xử lý khi bấm nút "Tung xu"
@app.on_callback_query(filters.regex(r"flip:(\d+)"))
async def coin_flip_callback(client, callback_query: CallbackQuery):
    user_id = int(callback_query.data.split(":")[1])
    
    # Kiểm tra nếu người bấm nút là người ra lệnh
    if callback_query.from_user.id != user_id:
        await callback_query.answer("Bạn không thể tung vì không phải người cược!", show_alert=True)
        return

    await callback_query.edit_message_text(f"{E_WAIT} Đang tung đồng xu cho bạn...", reply_markup=None, parse_mode=ParseMode.HTML)

    # Gửi GIF "tung xu" nếu file tồn tại, nếu không thì chỉ chờ
    gif_message = None
    if os.path.exists(GIF_PATH):
        try:
            gif_message = await callback_query.message.reply_animation(animation=GIF_PATH)
        except (ValueError, OSError):
            pass
    
    # Hiệu ứng chờ trong 3 giây
    await asyncio.sleep(3)

    # Tung đồng xu (sấp hoặc ngửa)
    result = random.choice(["🪙 Sấp", "🪙 Ngửa"])

    # Xóa GIF sau khi đã chờ xong (nếu đã gửi)
    if gif_message:
        await gif_message.delete()

    await callback_query.edit_message_text(f"{E_PARTY} Kết quả sau khi tung đồng xu: <b>{result}</b>", reply_markup=None, parse_mode=ParseMode.HTML)

    
# Danh sách các câu trả lời ngẫu nhiên (dùng khi chỉ nhắc "Dora" mà không hỏi gì) – emoji từ emoji.py
responses = [
    f"Ai gọi DoraSuper đấy? {E_SEARCH}",
    f"Nhắc đến DoraSuper làm gì thế? {E_MENU}",
    f"Dora ở đây, ai cần gì nào? {E_PARTY}",
    f"Dora không muốn xuất hiện đâu nhé! {E_COFFEE}",
    f"Bạn vừa gọi Dora, đừng nói là không! {E_QUESTION}",
    f"Hình như có ai đó nhắc đến Dora? {E_SEARCH}",
    f"Gọi Dora có việc gì không, hay chỉ muốn vui chơi? {E_PARTY}",
    f"Dora đã nghe thấy tiếng gọi từ xa! {E_BELL}",
    f"Ồ, Dora được gọi lên sân khấu à? {E_MEGAPHONE}",
    f"Dora đang ngủ, ai lại làm phiền thế này! {E_WAIT}",
    f"Dora đây! Muốn gì nào, bạn ơi? {E_HEART}",
    f"Dora xuất hiện trong một cuộc gọi bí ẩn... {E_SPARKLE}",
    f"Dora nghe rõ, sao cơ? {E_MUSIC}",
    f"Lại là DoraSuper, chắc có chuyện gì hệ trọng! {E_WARN}",
    f"Bạn vừa nhắc đến Dora hả? Cẩn thận đó! {E_WARN}",
    f"Dora sắp bùng nổ vì bị gọi quá nhiều rồi! {E_FIRE}",
    f"Ai lại đang tìm DoraSuper lừng danh Dora vậy? {E_SEARCH}",
    f"Gọi Dora một phát, chắc chắn có điều bí ẩn! {E_SEARCH}",
    f"Nhắc đến Dora là phải cẩn trọng nhé! {E_WARN}",
    f"Dora có mặt, có ai cần được giúp đỡ không? {E_SHIELD}",
    f"Bạn vừa khơi mào một cuộc phiêu lưu của Dora! {E_PIN_LOC}",
    f"Chào mừng đến với thế giới của Dora! {E_GLOBE}",
    f"Có ai đang nhắc đến một huyền thoại tên Dora không? {E_STAR}",
    f"Gọi Dora thế này, chắc lại có chuyện lớn rồi! {E_SOS}",
    f"Bạn đã đánh thức con quái vật Dora! {E_FIRE}",
    f"Dora nghe thấy tiếng gọi từ vũ trụ xa xôi! {E_SPARKLE}",
    f"Đừng có mà đùa với Dora nhé! {E_HEART3}",
    f"Dora vừa nghe thấy một tiếng gọi rất lạ... {E_ROCKET}",
    f"Dora đây, ai gọi thế? {E_HEART}",
    f"Gọi Dora thì phải có lý do chính đáng nhé! {E_NOTE}",
    f"Một lời nhắc đến Dora có thể làm rung chuyển thế giới! {E_THUNDER}",
]


def _is_bot_mentioned(message) -> bool:
    """Kiểm tra bot có bị @mention trong tin nhắn không (dùng khi bật Privacy mode)."""
    raw = (message.text or message.caption or "") or ""
    if not raw.strip() or not BOT_USERNAME:
        return False
    return f"@{BOT_USERNAME}".lower() in raw.lower()


def _is_reply_to_bot_ai(message) -> bool:
    """Tin nhắn có phải là reply vào tin của bot không (để trả lời tiếp, kể cả có gọi Dora trong tin)."""
    reply = message.reply_to_message
    # Câu hỏi follow-up có thể nằm ở text hoặc caption
    current_text = (message.text or message.caption or "").strip()
    if not reply or not current_text:
        return False
    # Tin được reply có từ bot gửi không (chỉ cần reply vào tin của bot → coi là follow-up)
    from_id = None
    if reply.from_user:
        from_id = reply.from_user.id
    elif reply.sender_chat:
        from_id = reply.sender_chat.id
    if from_id is None or getattr(app.me, "id", None) is None:
        return False
    return from_id == app.me.id


# Từ khóa khi reply user + gõ (hoặc @Bot + gõ) → thực hiện lệnh admin
_DORA_CMD_MUTE = (
    "khoá mõm", "khóa mõm", "khoa mom", "khóa mom","cấm chat",
    "khoá mồm", "khóa mồm", "khoa mồm",
    "mute", "tắt tiếng", "im mồm", "im mõm", "câm mồm", "câm mõm",
    "khoá theo thời gian", "khóa theo thời gian", "mute theo thời gian", "tắt tiếng theo thời gian",
)
_DORA_CMD_UNMUTE = ("bỏ mute", "bo mute", "bỏ khoá mõm", "bỏ khóa mõm", "unmute", "boimmom", "bỏ immom")
_DORA_CMD_KICK = ("xoá khỏi nhóm", "cút", "cút đi", "xóa khỏi nhóm", "xoa khoi nhom", "xoá khỏi", "xóa khỏi")
_DORA_CMD_BAN = ("cấm", "ban", "cam")
_DORA_CMD_UNBAN = ("bỏ cấm", "bo cam", "unban", "bocam")


def _normalize_for_cmd(t: str) -> str:
    """Chuẩn hóa Unicode để so khớp từ khóa (khoá/khóa, v.v.) bất kể cách gõ."""
    return unicodedata.normalize("NFC", t.lower().strip())


async def _try_execute_dora_command(message, text: str) -> bool:
    """
    Nếu tin nhắn là reply vào một user và text chứa từ lệnh (khoá mõm, xoá khỏi nhóm, cấm...)
    thì thực hiện mute/kick/ban với user được reply. Trả về True nếu đã xử lý (thành công hoặc báo lỗi).
    """
    if not text or not message.from_user:
        return False
    chat = message.chat
    if chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return False

    t = _normalize_for_cmd(text)
    _n = lambda p: unicodedata.normalize("NFC", p)
    has_cmd = (
        any(_n(p) in t for p in _DORA_CMD_MUTE)
        or any(_n(p) in t for p in _DORA_CMD_UNMUTE)
        or any(_n(p) in t for p in _DORA_CMD_KICK)
        or any(_n(p) in t for p in _DORA_CMD_BAN)
        or any(_n(p) in t for p in _DORA_CMD_UNBAN)
    )
    if not has_cmd:
        return False

    # Từ khoá chỉ hoạt động khi có "Dora" trong tin (VD: Dora khoá mõm, @Bot Dora đá)
    if not _has_dora_text(text):
        await message.reply(
            f"{E_WARN} Phải nhắc <b>Dora</b> trước từ khoá. VD: <b>Dora khoá mõm</b>, <b>Dora đá</b>, <b>Dora bỏ cấm</b>.",
            parse_mode=ParseMode.HTML,
        )
        return True

    # Có lệnh + có Dora → bắt buộc phải reply đúng tin của người cần xử lý
    reply = message.reply_to_message
    if not reply or not reply.from_user:
        await message.reply(
            f"{E_WARN} Hãy <b>reply trực tiếp vào tin nhắn</b> của người cần đá/khoá/cấm (hoặc bỏ mute/bỏ cấm), rồi gõ từ khoá.",
            parse_mode=ParseMode.HTML,
        )
        return True

    target_id = reply.from_user.id
    sender_id = message.from_user.id
    bot_id = getattr(app.me, "id", None)

    if target_id == bot_id or target_id == sender_id:
        await message.reply(
            f"{E_WARN} Hãy reply vào tin của <b>người cần đá</b>, không reply tin của bot hay tin của bạn.",
            parse_mode=ParseMode.HTML,
        )
        return True
    if target_id in (SUDO or []):
        await message.reply(f"{E_WARN} Không thể thực hiện với user này.", parse_mode=ParseMode.HTML)
        return True
    try:
        admins = await list_admins(chat.id)
        if target_id in admins:
            await message.reply(
                f"{E_WARN} Không thể đá/khoá/cấm quản trị viên trong nhóm.",
                parse_mode=ParseMode.HTML,
            )
            return True
    except Exception as e:
        LOGGER.warning("list_admins in dora cmd: %s", e)
        await message.reply(
            f"{E_WARN} Không thể kiểm tra quyền, thử lại sau.",
            parse_mode=ParseMode.HTML,
        )
        return True

    # Sudo không cần quyền admin trong nhóm vẫn ra lệnh khoá/đá/cấm
    if sender_id not in (SUDO or []):
        perms = await member_permissions(chat.id, sender_id)
        if "can_restrict_members" not in perms:
            await message.reply(
                f"{E_WARN} Bạn cần quyền hạn chế thành viên (restrict) để dùng lệnh Dora này.",
                parse_mode=ParseMode.HTML,
            )
            return True

    try:
        target_mention = reply.from_user.mention
    except Exception:
        target_mention = f"ID {target_id}"

    # Bỏ cấm — kiểm tra trước BAN để "bỏ cấm" không match "cấm"
    if any(_n(p) in t for p in _DORA_CMD_UNBAN):
        try:
            await app.unban_chat_member(chat.id, target_id)
            await remove_chat_ban(chat.id, target_id)
            await message.reply(
                f"{E_SUCCESS} Đã bỏ cấm {target_mention}.",
                parse_mode=ParseMode.HTML,
            )
            return True
        except Exception as e:
            LOGGER.warning("Dora unban failed: %s", e)
            await message.reply(
                f"{E_WARN} Không thể bỏ cấm. Lỗi: {str(e)[:80]}",
                parse_mode=ParseMode.HTML,
            )
            return True

    # Bỏ mute — kiểm tra trước MUTE
    if any(_n(p) in t for p in _DORA_CMD_UNMUTE):
        try:
            await app.unban_chat_member(chat.id, target_id)
            await remove_chat_mute(chat.id, target_id)
            await message.reply(
                f"{E_SUCCESS} Đã bỏ khoá mõm {target_mention}.",
                parse_mode=ParseMode.HTML,
            )
            return True
        except Exception as e:
            LOGGER.warning("Dora unmute failed: %s", e)
            await message.reply(
                f"{E_WARN} Không thể bỏ mute. Lỗi: {str(e)[:80]}",
                parse_mode=ParseMode.HTML,
            )
            return True

    if any(_n(p) in t for p in _DORA_CMD_MUTE):
        until_date = None
        # Parse thời gian nếu có (vd: "1h", "30m", "2d" hoặc "khoá theo thời gian 1h")
        time_match = re.search(r"(\d{1,4})\s*([mhd])", t)
        if "theo thời gian" in t or "theo thoi gian" in t:
            if not time_match:
                await message.reply(
                    f"{E_WARN} Gõ thêm thời gian, ví dụ: <b>khoá theo thời gian 1h</b> hoặc <b>30m</b>, <b>2d</b>.",
                    parse_mode=ParseMode.HTML,
                )
                return True
        if time_match:
            num, unit = int(time_match.group(1)), time_match.group(2).lower()
            if unit == "m":
                until_date = datetime.now() + timedelta(minutes=min(num, 59))
            elif unit == "h":
                until_date = datetime.now() + timedelta(hours=min(num, 48))
            elif unit == "d":
                until_date = datetime.now() + timedelta(days=min(num, 365))
        try:
            if until_date:
                await app.restrict_chat_member(
                    chat.id, target_id,
                    permissions=ChatPermissions(all_perms=False),
                    until_date=until_date,
                )
                await add_chat_mute(chat.id, target_id, int(until_date.timestamp()))
                await message.reply(
                    f"{E_LOCK} Đã khoá mõm {target_mention} đến {until_date.strftime('%H:%M %d/%m')}.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await app.restrict_chat_member(chat.id, target_id, permissions=ChatPermissions(all_perms=False))
                await add_chat_mute(chat.id, target_id, 0)
                await message.reply(
                    f"{E_LOCK} Đã khoá mõm {target_mention}.",
                    parse_mode=ParseMode.HTML,
                )
            return True
        except Exception as e:
            LOGGER.warning("Dora mute failed: %s", e)
            await message.reply(
                f"{E_WARN} Không thể khoá mõm (bot cần quyền hạn chế thành viên trong nhóm).",
                parse_mode=ParseMode.HTML,
            )
            return True

    if any(_n(p) in t for p in _DORA_CMD_KICK):
        try:
            await app.ban_chat_member(chat.id, target_id)
            await asyncio.sleep(0.5)
            await app.unban_chat_member(chat.id, target_id)
            await message.reply(
                f"{E_SUCCESS} Đã đá {target_mention} khỏi nhóm.",
                parse_mode=ParseMode.HTML,
            )
            return True
        except Exception as e:
            LOGGER.warning("Dora kick failed chat_id=%s target_id=%s: %s", chat.id, target_id, e)
            await message.reply(
                f"{E_WARN} Không thể đá khỏi nhóm (bot cần quyền ban thành viên). Lỗi: {str(e)[:100]}",
                parse_mode=ParseMode.HTML,
            )
            return True

    if any(_n(p) in t for p in _DORA_CMD_BAN):
        try:
            await app.ban_chat_member(chat.id, target_id)
            await add_chat_ban(chat.id, target_id)
            await message.reply(
                f"{E_LOCK} Đã cấm {target_mention} khỏi nhóm.",
                parse_mode=ParseMode.HTML,
            )
            return True
        except Exception as e:
            LOGGER.warning("Dora ban failed chat_id=%s target_id=%s: %s", chat.id, target_id, e)
            await message.reply(
                f"{E_WARN} Không thể cấm (bot cần quyền ban thành viên). Lỗi: {str(e)[:100]}",
                parse_mode=ParseMode.HTML,
            )
            return True

    return False


async def _send_dora_reply(client, chat_id, reply_to_id, question, from_user, strings, reply_context=None, replied_to_user=None):
    """Gửi phản hồi AI hoặc câu random khi gọi Dora (dùng chung cho handler Dora và handler @mention)."""
    import re
    if len(question) > 3:
        from dorasuper.plugins.ai import ask_gemini
        from pyrogram.errors import MessageTooLong

        try:
            wait_msg = await client.send_message(
                chat_id, f"{E_PENDING} Hmmmmm{E_TYMMY}! Đợi em chút xíu nha{E_LOADING}", reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML
            )
        except Exception:
            wait_msg = await client.send_message(chat_id, f"Hmmmmm{E_TYMMY}! Đợi em chút xíu nha{E_LOADING}", reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        try:
            user_name = from_user.first_name if from_user else "Người dùng"
            prompt = f"[{user_name}]: {question.strip()}"
            if reply_context and reply_context.strip():
                prompt += f"\n(Ngữ cảnh reply: {reply_context[:500].strip()})"
            if replied_to_user:
                prompt += f"\n(Tin được reply là của: {replied_to_user.first_name}. Khi hỏi 'ai đây' / 'là ai' thì trả lời đó là người này – {replied_to_user.first_name}.)"
            user_id = from_user.id if from_user else None
            answer = await ask_gemini(prompt, user_id=user_id, user_name=user_name)
            if not (answer and str(answer).strip()):
                await wait_msg.edit(f"{E_WARN} Dora chưa trả lời được. Thử lại hoặc dùng <code>/ai</code>.", parse_mode=ParseMode.HTML)
                return
            from dorasuper.plugins.ai import _apply_emoji_placeholders, _ACTION_PHRASES, _escape_answer_for_html
            answer = _apply_emoji_placeholders(answer)
            # Escape HTML và giữ link clickable (tránh lỗi khi AI trả về có URL)
            answer_safe = _escape_answer_for_html(answer)
            def _actions_to_emoji(m):
                inner = m.group(1).strip()
                for phrase, emoji in _ACTION_PHRASES:
                    if inner == phrase.strip():
                        return emoji + " "
                return f"<b>{inner}</b>"  # inner đã được escape trong _escape_answer_for_html
            answer_safe = re.sub(r"\*([^*]+)\*", _actions_to_emoji, answer_safe)
            safe_name = html.escape(user_name)
            answer_safe = re.sub(r"\*\*([^*]+)\*\*", lambda m: f"<b>{m.group(1)}</b>", answer_safe)
            answer_safe = answer_safe.replace("&lt;b&gt;" + safe_name + "&lt;/b&gt;", "\x00KEEP\x00")
            answer_safe = answer_safe.replace(safe_name, f"<b>{safe_name}</b>")
            answer_safe = answer_safe.replace("\x00KEEP\x00", "<b>" + safe_name + "</b>")
            if replied_to_user:
                safe_replied = html.escape(replied_to_user.first_name)
                answer_safe = answer_safe.replace("&lt;b&gt;" + safe_replied + "&lt;/b&gt;", safe_replied)
                answer_safe = answer_safe.replace(safe_replied, f"<b>{safe_replied}</b>")
            result = f"{E_BOT} <b>DoraSuper</b>{E_VUAM}\n<blockquote expandable>{answer_safe}</blockquote>"
            try:
                await wait_msg.edit(result, parse_mode=ParseMode.HTML)
            except MessageTooLong:
                from dorasuper.helper.tools import rentry
                url = await rentry(answer)
                await wait_msg.edit(f"{E_BOT} <b>Câu trả lời quá dài:</b>\n{url}", parse_mode=ParseMode.HTML)
            except Exception:
                try:
                    await wait_msg.edit(result, parse_mode=ParseMode.DISABLED)
                except MessageTooLong:
                    from dorasuper.helper.tools import rentry
                    url = await rentry(answer)
                    await wait_msg.edit(f"{E_BOT} Câu trả lời quá dài:\n{url}", parse_mode=ParseMode.DISABLED)
        except Exception as e:
            LOGGER.exception("_send_dora_reply: %s", e)
            try:
                await wait_msg.edit(f"{E_WARN} Dora chưa trả lời được. Thử lại hoặc dùng <code>/ai</code>.", parse_mode=ParseMode.HTML)
            except Exception:
                pass
    else:
        response = random.choice(responses)
        try:
            await client.send_message(chat_id, response, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        except Exception:
            fallback = re.sub(r'<emoji\s+id="[^"]*">([^<]*)</emoji>', lambda x: x.group(1), response)
            await client.send_message(chat_id, fallback, reply_to_message_id=reply_to_id)


# /khoamom, /da – Khoá mõm / đá (reply vào tin người cần xử lý). Luôn hoạt động kể cả khi bật Group Privacy.
@app.on_message(filters.command(["khoamom", "khoa_mom"], COMMAND_HANDLER) & filters.group)
async def cmd_khoamom(c, m):
    if await _try_execute_dora_command(m, "khoá mõm"):
        return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await m.reply(
            f"{E_WARN} Reply vào tin nhắn của người cần khoá mõm rồi gõ <code>/khoamom</code>.",
            parse_mode=ParseMode.HTML,
        )


@app.on_message(filters.command(["da", "kick"], COMMAND_HANDLER) & filters.group)
async def cmd_da(c, m):
    if await _try_execute_dora_command(m, "đá khỏi"):
        return
    if not m.reply_to_message or not m.reply_to_message.from_user:
        await m.reply(
            f"{E_WARN} Reply vào tin nhắn của người cần đá rồi gõ <code>/da</code> hoặc <code>/kick</code>.",
            parse_mode=ParseMode.HTML,
        )


# /dora [câu hỏi] – Gọi Dora bằng lệnh (hoạt động khi reply, kể cả khi bật Group Privacy)
@app.on_message(filters.command("dora", COMMAND_HANDLER))
@use_chat_lang()
async def cmd_dora(c, m, strings):
    if len(m.command) > 1:
        question = m.text.split(maxsplit=1)[1].strip()
    elif m.reply_to_message and (m.reply_to_message.text or m.reply_to_message.caption):
        question = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()
    else:
        await m.reply(
            f"{E_BOT} Dùng: <code>/dora [câu hỏi]</code> hoặc reply tin nhắn + <code>/dora</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    reply_context = None
    replied_to_user = None
    if m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id != getattr(app.me, "id", None):
        reply_context = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()
        replied_to_user = m.reply_to_message.from_user
    await _send_dora_reply(c, m.chat.id, m.id, question, m.from_user, strings, reply_context=reply_context, replied_to_user=replied_to_user)


# Reply vào tin AI của bot → trả lời tiếp không cần gõ "Dora" nữa (ưu tiên group 0)
@app.on_message(filters.reply & (filters.text | filters.caption) & ~filters.via_bot, group=0)
@use_chat_lang()
async def reply_to_ai_followup(c, m, strings):
    if not _is_reply_to_bot_ai(m):
        return
    question = (m.text or m.caption or "").strip()
    if not question:
        return
    try:
        await _send_dora_reply(c, m.chat.id, m.id, question, m.from_user, strings)
    except Exception as e:
        LOGGER.exception("reply_to_ai_followup: %s", e)
        try:
            await m.reply(f"{E_WARN} Dora chưa trả lời được. Thử lại hoặc dùng <code>/ai</code>.", parse_mode=ParseMode.HTML)
        except Exception:
            pass


# Một handler duy nhất: "Dora" (AI trả lời) HOẶC từ khoá (khoá mõm/đá/cấm) — nhóm + chat riêng (lệnh khoá/đá chỉ có hiệu lực trong nhóm)
def _dora_strings(key):
    return key

def _has_dora_text(text: str) -> bool:
    return bool(regex.search(r"(?i).*[DdĐđ]ora.*", text or ""))

def _has_cmd_keyword(text: str) -> bool:
    if not (text or "").strip():
        return False
    t = _normalize_for_cmd(text)
    _n = lambda p: unicodedata.normalize("NFC", p)
    return (
        any(_n(p) in t for p in _DORA_CMD_MUTE)
        or any(_n(p) in t for p in _DORA_CMD_UNMUTE)
        or any(_n(p) in t for p in _DORA_CMD_KICK)
        or any(_n(p) in t for p in _DORA_CMD_BAN)
        or any(_n(p) in t for p in _DORA_CMD_UNBAN)
    )

def _dora_or_cmd_filter(_, __, m):
    raw = (m.text or m.caption or "") or ""
    # Khi dùng / lệnh thì thôi — chỉ handler lệnh chạy
    if raw.strip().startswith("/"):
        return False
    # Tin hiện tại có "Dora" → gọi Dora (hoặc từ khoá)
    if _has_dora_text(raw):
        return True
    # Reply kèm nội dung: reply vào tin có "Dora" HOẶC reply vào tin của bot (follow-up) → vào handler
    reply = m.reply_to_message
    if reply and raw.strip():
        replied_raw = (reply.text or reply.caption or "") or ""
        if _has_dora_text(replied_raw):
            return True
        # Reply vào tin của bot (bất kể nội dung) → follow-up Dora
        if _is_reply_to_bot_ai(m):
            return True
    return False

@app.on_message(
    (filters.text | filters.caption) & ~filters.via_bot & (filters.group | filters.private) & filters.create(_dora_or_cmd_filter),
    group=-1,
)
async def reply_to_dora(c, m):
    import re

    try:
        full_text = (m.text or m.caption or "").strip()
        LOGGER.info("reply_to_dora triggered chat_id=%s text=%r", m.chat.id, (full_text or "")[:60])
        # Reply vào tin của bot → xử lý follow-up ngay tại đây (trả lời tiếp, kể cả có gọi Dora)
        if _is_reply_to_bot_ai(m):
            question = re.sub(r"(?i)[dDđĐ]ora[\s,]*(?:ơi|à|ê|nè)?[\s,]*", "", full_text).strip() or full_text
            if question:
                await _send_dora_reply(c, m.chat.id, m.id, question, m.from_user, _dora_strings)
            return
        # Nếu có @mention bot thì để handler reply_to_mention_dora xử lý, tránh trùng
        if _is_bot_mentioned(m):
            return

        # Từ khoá (khoá mõm / đá / cấm) → thực hiện mute/kick/ban
        if _has_cmd_keyword(full_text):
            await _try_execute_dora_command(m, full_text)

        # AI trả lời khi: (1) tin hiện tại có "Dora", hoặc (2) reply vào tin có "Dora" (gọi Dora rồi reply câu hỏi)
        has_dora_in_msg = _has_dora_text(full_text)
        is_reply_to_dora_msg = False
        if m.reply_to_message and full_text:
            replied_raw = (m.reply_to_message.text or m.reply_to_message.caption or "") or ""
            is_reply_to_dora_msg = _has_dora_text(replied_raw)
        if not has_dora_in_msg and not is_reply_to_dora_msg:
            return
        reply_context = None
        replied_to_user = None
        if m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id != getattr(app.me, "id", None):
            reply_context = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()
            replied_to_user = m.reply_to_message.from_user
        if has_dora_in_msg:
            question = re.sub(r"(?i)[dDđĐ]ora[\s,]*(?:ơi|à|ê|nè)?[\s,]*", "", full_text).strip() or full_text
        else:
            question = full_text.strip()
        await _send_dora_reply(c, m.chat.id, m.id, question, m.from_user, _dora_strings, reply_context=reply_context, replied_to_user=replied_to_user)
    except Exception as e:
        LOGGER.exception("reply_to_dora: %s", e)
        try:
            await m.reply(
                f"{E_WARN} Dora chưa trả lời được. Thử lại hoặc dùng <code>/ai</code>.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


# Chỉ khi có @mention bot (dự phòng khi bật Privacy hoặc muốn gọi bằng @)
@app.on_message((filters.text | filters.caption) & filters.mentioned & ~filters.via_bot, group=1)
@use_chat_lang()
async def reply_to_mention_dora(c, m, strings):
    if not _is_bot_mentioned(m):
        return
    import re
    text = (m.text or m.caption or "").strip()
    await _try_execute_dora_command(m, text)
    # AI chỉ trả lời khi có từ "Dora" — chỉ từ khoá (@Bot khoá mõm) thì không gọi AI
    if not _has_dora_text(text):
        return
    reply_context = None
    replied_to_user = None
    if m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id != getattr(app.me, "id", None):
        reply_context = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()
        replied_to_user = m.reply_to_message.from_user
    question = re.sub(r"@" + re.escape(BOT_USERNAME or "") + r"\s*", "", text, flags=re.I).strip()
    question = re.sub(r"(?i)[dDđĐ]ora[\s,]*(?:ơi|à|ê|nè)?[\s,]*", "", question).strip() or question
    await _send_dora_reply(c, m.chat.id, m.id, question, m.from_user, strings, reply_context=reply_context, replied_to_user=replied_to_user)