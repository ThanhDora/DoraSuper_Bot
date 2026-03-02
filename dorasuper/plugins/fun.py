import textwrap
from asyncio import gather
import asyncio
import logging
import os
import random
import regex
import uuid
import tempfile
from logging import getLogger
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageIdInvalid, PeerIdInvalid, ReactionInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatPermissions
from dorasuper import app, user, BOT_USERNAME
from dorasuper.emoji import (
    E_NOTE, E_SEARCH, E_WARN, E_BOT, E_PARTY, E_WAIT, E_MSG,
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
from database.chat_ban_db import add_chat_ban

LOGGER = getLogger(__name__)

__MODULE__ = "🎮 Fun & Game"
__HELP__ = """
<blockquote>🎲 <b>Fun & Game</b>

/xucxac, /tungxx – Tung xúc xắc (dice)
/tungxu [sấp|ngửa] – Tung đồng xu, đoán sấp hoặc ngửa

👤 /anony [tin nhắn] – Gửi tin nhắn nặc danh (reply tin người nhận)
💬 Chỉ gọi "Dora" + câu hỏi (không cần @ hay /): trong nhóm phải tắt Group Privacy thì bot mới nhận được. Cách tắt: BotFather → chọn bot → Bot Settings → Group Privacy → Turn Off.</blockquote>
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
    if not message.text or not BOT_USERNAME:
        return False
    text_lower = message.text.lower()
    return f"@{BOT_USERNAME}".lower() in text_lower


def _is_reply_to_bot_ai(message) -> bool:
    """Tin nhắn có phải là reply vào tin AI của bot không (để trả lời tiếp không cần gọi Dora)."""
    reply = message.reply_to_message
    if not reply or not message.text or not message.text.strip():
        return False
    # Tin được reply có từ bot gửi không
    from_id = None
    if reply.from_user:
        from_id = reply.from_user.id
    elif reply.sender_chat:
        from_id = reply.sender_chat.id
    if from_id is None or getattr(app.me, "id", None) is None:
        return False
    if from_id != app.me.id:
        return False
    # Tin đó có phải là câu trả lời AI (có "DoraSuper" trong nội dung)
    replied_text = (reply.text or reply.caption or "") or ""
    return "DoraSuper" in replied_text


# Từ khóa khi gọi Dora + reply user → thực hiện lệnh admin (khoá mõm / đá / cấm)
_DORA_CMD_MUTE = ("khoá mõm", "khóa mõm", "mute", "tắt tiếng", "im mồm", "câm mồm", "khoa mom", "khóa mom")
_DORA_CMD_KICK = ("xoá khỏi nhóm", "xóa khỏi nhóm", "xoa khoi nhom", "đá khỏi", "đá ra", "da khoi", "kick", "xoá khỏi", "xóa khỏi", "đá đi")
_DORA_CMD_BAN = ("cấm", "ban", "cam")


async def _try_execute_dora_command(message, text: str) -> bool:
    """
    Nếu tin nhắn là reply vào một user và text chứa từ lệnh (khoá mõm, xoá khỏi nhóm, cấm...)
    thì thực hiện mute/kick/ban với user được reply. Trả về True nếu đã xử lý (thành công hoặc báo lỗi).
    """
    if not text or not message.from_user:
        return False
    chat = message.chat
    if chat.type not in ("supergroup", "group"):
        return False

    t = text.lower().strip()
    has_cmd = any(phrase in t for phrase in _DORA_CMD_MUTE) or any(phrase in t for phrase in _DORA_CMD_KICK) or any(phrase in t for phrase in _DORA_CMD_BAN)
    if not has_cmd:
        return False

    # Có lệnh kick/mute/ban → bắt buộc phải reply đúng tin của người cần xử lý
    reply = message.reply_to_message
    if not reply or not reply.from_user:
        await message.reply(
            f"{E_WARN} Hãy <b>reply trực tiếp vào tin nhắn</b> của người cần đá/khoá/cấm, rồi gõ Dora kick (hoặc khoá mõm, cấm).",
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
    except Exception:
        return False

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

    if any(phrase in t for phrase in _DORA_CMD_MUTE):
        try:
            await app.restrict_chat_member(chat.id, target_id, permissions=ChatPermissions(all_perms=False))
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

    if any(phrase in t for phrase in _DORA_CMD_KICK):
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

    if any(phrase in t for phrase in _DORA_CMD_BAN):
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


async def _send_dora_reply(client, chat_id, reply_to_id, question, from_user, strings, reply_context=None):
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
        user_name = from_user.first_name if from_user else "Người dùng"
        prompt = f"[{user_name}]: {question.strip()}"
        if reply_context and reply_context.strip():
            prompt += f"\n(Ngữ cảnh reply: {reply_context[:500].strip()})"
        answer = await ask_gemini(prompt)

        def _actions_to_emoji(m):
            inner = m.group(1)
            inner = inner.replace("mỉm cười nghiêng đầu", E_SIDEWAYS).replace("nháy mắt", E_WINK).replace("cắn môi", E_BITE_YOUR_LIPS)
            return inner.strip()
        answer = re.sub(r"\*([^*]+)\*", _actions_to_emoji, answer)
        result = f"{E_BOT} <b>DoraSuper</b>\n\n{answer}"
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
    else:
        response = random.choice(responses)
        try:
            await client.send_message(chat_id, response, reply_to_message_id=reply_to_id, parse_mode=ParseMode.HTML)
        except Exception:
            fallback = re.sub(r'<emoji\s+id="[^"]*">([^<]*)</emoji>', lambda x: x.group(1), response)
            await client.send_message(chat_id, fallback, reply_to_message_id=reply_to_id)


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
    if m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id != getattr(app.me, "id", None):
        reply_context = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()
    await _send_dora_reply(c, m.chat.id, m.id, question, m.from_user, strings, reply_context=reply_context)


# Reply vào tin AI của bot → trả lời tiếp không cần gõ "Dora" nữa (ưu tiên group 0)
@app.on_message(filters.reply & filters.text & ~filters.via_bot, group=0)
@use_chat_lang()
async def reply_to_ai_followup(c, m, strings):
    if not _is_reply_to_bot_ai(m):
        return
    question = (m.text or "").strip()
    await _send_dora_reply(c, m.chat.id, m.id, question, m.from_user, strings)


# Gọi "Dora" / "Dora ơi" trong tin – group -1 để chạy trước, không dùng use_chat_lang tránh lỗi locale
def _dora_strings(key):
    return key

def _has_dora_text(_, __, m):
    return bool(regex.search(r"(?i).*[DdĐđ]ora.*", (m.text or m.caption or "") or ""))

@app.on_message(
    (filters.text | filters.caption) & ~filters.via_bot & filters.create(_has_dora_text),
    group=-1,
)
async def reply_to_dora(c, m):
    import re

    try:
        LOGGER.info("reply_to_dora triggered chat_id=%s", m.chat.id)
        # Nếu là reply vào tin AI của bot thì để handler reply_to_ai_followup xử lý
        if _is_reply_to_bot_ai(m):
            return
        # Nếu có @mention bot thì để handler bên dưới xử lý, tránh trùng
        if _is_bot_mentioned(m):
            return

        full_text = (m.text or m.caption or "").strip()
        if await _try_execute_dora_command(m, full_text):
            return

        # Ngữ cảnh: nếu reply tin của user thì đưa nội dung tin đó cho AI
        reply_context = None
        if m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id != getattr(app.me, "id", None):
            reply_context = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()

        # Lấy phần câu hỏi (bỏ "Dora", "Dora ơi", ...)
        question = re.sub(r"(?i)[dDđĐ]ora[\s,]*(?:ơi|à|ê|nè)?[\s,]*", "", full_text).strip()

        await _send_dora_reply(c, m.chat.id, m.id, question, m.from_user, _dora_strings, reply_context=reply_context)
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
@app.on_message(filters.text & filters.mentioned & ~filters.via_bot, group=1)
@use_chat_lang()
async def reply_to_mention_dora(c, m, strings):
    if not _is_bot_mentioned(m):
        return
    import re
    text = (m.text or "").strip()
    if await _try_execute_dora_command(m, text):
        return
    reply_context = None
    if m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id != getattr(app.me, "id", None):
        reply_context = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()
    question = re.sub(r"@" + re.escape(BOT_USERNAME or "") + r"\s*", "", text, flags=re.I).strip()
    question = re.sub(r"(?i)[dDđĐ]ora[\s,]*(?:ơi|à|ê|nè)?[\s,]*", "", question).strip() or question
    await _send_dora_reply(c, m.chat.id, m.id, question, m.from_user, strings, reply_context=reply_context)