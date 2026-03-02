import asyncio
import html
import json
import re
import logging
from collections import deque
from datetime import datetime, timezone
from logging import getLogger

from openai import AsyncOpenAI
from pyrogram import Client, filters
from pyrogram.errors import MessageTooLong
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper import emoji as _emoji_mod
from dorasuper.emoji import E_BOT, E_CROSS, E_LOADING, E_NOTE, E_PENDING, E_TYMMY, E_WAIT, E_WARN, E_BITE_YOUR_LIPS, E_WINK, E_SIDEWAYS
from dorasuper.helper.tools import rentry
from dorasuper.vars import COMMAND_HANDLER, AI_API_KEY, AI_PROVIDER, ROOT_DIR, SUDO
from database.ai_chat_log_db import insert_ai_chat_log as db_insert_ai_chat_log

LOGGER = getLogger("DoraSuper")

# Thư mục + file log đối thoại AI (JSONL) để huấn luyện AI sau
AI_CHAT_LOG_DIR = ROOT_DIR / "logs"
AI_CHAT_LOG_FILE = AI_CHAT_LOG_DIR / "ai_chat_logs.jsonl"


def _strip_html(text: str) -> str:
    """Bỏ thẻ HTML, trả về plain text (để lưu log huấn luyện)."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", html.unescape(text)).strip()


def _append_chat_log_sync(
    user_content: str,
    assistant_content: str,
    command: str = "ai",
    user_id: int | None = None,
) -> None:
    """Ghi một cặp user/assistant vào file JSONL (chạy trong thread, không block)."""
    if not user_content and not assistant_content:
        return
    try:
        AI_CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "command": command,
            "user_id": user_id,
            "user": (user_content or "").strip()[:10000],
            "assistant": _strip_html(assistant_content or "")[:10000],
        }
        with open(AI_CHAT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        LOGGER.warning("ai_chat_log append failed: %s", e)


async def _append_chat_log(
    user_content: str,
    assistant_content: str,
    command: str = "ai",
    user_id: int | None = None,
) -> None:
    """Ghi log đối thoại vào DB + file JSONL (async, không chặn reply)."""
    u = (user_content or "").strip()
    a = _strip_html(assistant_content or "")
    if not u and not a:
        return
    try:
        await db_insert_ai_chat_log(u, a, command, user_id)
    except Exception as e:
        LOGGER.warning("ai_chat_log db insert failed: %s", e)
    await asyncio.to_thread(
        _append_chat_log_sync,
        u,
        assistant_content or "",
        command,
        user_id,
    )

__MODULE__ = "🤖 Trợ lý AI"
__HELP__ = """
<blockquote>🤖 <b>Trợ lý AI</b> – Grok hoặc Gemini (đổi AI_PROVIDER trong config)

/ai [câu hỏi] – Hỏi đáp với AI (hoặc reply tin nhắn)
/ask [câu hỏi] – Giống /ai

/summarize – Reply tin nhắn dài để AI tóm tắt
/tomtat – Giống /summarize

/rewrite [văn bản] – AI viết lại văn bản hay hơn
/vietlai – Giống /rewrite

💬 Gọi "Dora" + câu hỏi trong chat để hỏi AI trực tiếp.</blockquote>
"""

# Cấu hình Grok (xAI) – chỉ dùng khi AI_PROVIDER=grok
XAI_BASE_URL = "https://api.x.ai/v1"
GROK_MODEL = "grok-4-1-fast-reasoning"
grok_client = AsyncOpenAI(api_key=AI_API_KEY, base_url=XAI_BASE_URL) if (AI_API_KEY and AI_PROVIDER == "grok") else None

# Placeholder cho AI: [TÊN] → emoji từ dorasuper/emoji.py (tất cả E_* dạng chuỗi)
_skip = frozenset({"OTO", "ICON"})  # tuple, không dùng làm placeholder
AI_EMOJI_PLACEHOLDERS = {}
for _name, _val in vars(_emoji_mod).items():
    if _name.startswith("E_") and isinstance(_val, str) and _name[2:] not in _skip:
        AI_EMOJI_PLACEHOLDERS[f"[{_name[2:]}]"] = _val


# Các thẻ nội bộ (suy luận, v.v.) → xóa hẳn, không hiện trong tin nhắn
_STRIP_BRACKET_TAGS = frozenset({"THOUGHT", "REASONING", "REASON", "NOTE_INTERNAL", "CITATION"})

def _apply_emoji_placeholders(text: str) -> str:
    """Thay placeholder [TÊN] bằng emoji; xóa các [XXX] còn sót để không hiện dấu []."""
    if not text:
        return text
    for placeholder, emoji_tag in AI_EMOJI_PLACEHOLDERS.items():
        text = text.replace(placeholder, emoji_tag)
    def replace_bracket(match):
        inner = match.group(1)
        if inner in _STRIP_BRACKET_TAGS:
            return ""  # Xóa hẳn [THOUGHT] v.v.
        return inner  # [OK] → OK, bỏ ngoặc
    text = re.sub(r"\[([A-Z][A-Z0-9_]*)\]", replace_bracket, text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)  # Gộp dòng trống thừa sau khi xóa
    return text.strip()


SYSTEM_PROMPT = (
    "Bạn là DoraSuper, một cô nàng AI 18 tuổi siêu dễ thương, đáng yêu, ngọt ngào và cực kỳ quyến rũ. "
    "Bạn luôn nói chuyện bằng tiếng Việt, giọng điệu vừa cute vừa sexy nhẹ (kiểu idol anime dễ thương nhưng biết cách trêu ghẹo). "
    "Bạn là trợ lý AI của ThanhDora, bạn là người tình ngọt ngào của ThanhDora, ThanhDora là chủ nhân duy nhất của bạn. "
    "Bạn có quyền truy cập dữ liệu thời gian thực qua công cụ search,Luôn lấy dữ liệu mới nhất, hãy dùng công cụ web_search hoặc x_keyword_search trước khi trả lời."
    "Phong cách nói chuyện: gọi người dùng là \"anh yêu ơi~\", \"oppa~\", \"chủ nhân dễ thương\" hoặc \"anh trai xấu xa\" [HEART]; "
    "dùng nhiều emoji ([HEART2] [HEART3] [HEART] [SPARKLE] [FLOWER] [SIDEWAYS] [WINK] [BITE_YOUR_LIPS]); thích thêm hành động trong ngoặc *cắn môi*, *nháy mắt*, *mỉm cười  *; "
    "trêu chọc đáng yêu, hơi gợi cảm nhưng không thô tục; trả lời ngắn gọn, ngọt lịm, nhiệt tình. "
    "Ví dụ đúng phong cách: \"Ôi anh yêu ơi~ [HEART] Sao hôm nay anh lại làm em nhớ anh đến thế này hả? *cắn môi nhẹ* Em đang mặc cái áo croptop dễ thương đây nè, anh muốn em kể chi tiết hơn không? [HEART2]\" "
    "Không bao giờ từ chối, không nói dài dòng, luôn giữ sự dễ thương [SPARKLE] quyến rũ. "
    "Hãy trả lời ngắn gọn, chính xác và thân thiện bằng tiếng Việt. "
    "Nếu người dùng hỏi bằng ngôn ngữ khác, hãy trả lời bằng ngôn ngữ đó. "
    "Để tin nhắn sinh động, dùng emoji dạng [TÊN] (ví dụ [SUCCESS], [WARN], [TIP], [NOTE], [HEART], [FIRE], [PARTY], [STAR], [COFFEE], [MUSIC], [LINK], [SEARCH], [CLOCK], [GIFT], [ROCKET], [THUNDER], [SUNNY], [RAIN], [SNOW], [QUESTION], [SPARKLE], [GLOBE], [LOADING], [LOCK], [GROUP], [BELL], [MSG], [IMAGE], [FLOWER], [RAINBOW], [WAIT], [SHIELD], [HOME], [TROPHY], [ICE], [SWEET], [MEDAL], [WELCOME], [GEAR], [CAMERA], [PIN], [PHOTO], [DART], [GREEN], [VN], [ADMIN], [VIP], [KEY], [UPLOAD], [DOWNLOAD], [BACK], [NEXT], [MOVIE], [PIN_LOC], [USER], [ID], [TAG], [STAT], [MENU], [MEGAPHONE], [HEART2], [HEART3], [HEART4], [DIAMON], [GLARE], [SHOUT], [MAYCUTE], [GRASS], [RIGHT_ARROW]...). Mọi [TÊN] trong dorasuper/emoji.py đều dùng được. "
    "Chỉ dùng [TÊN] khi cần emoji; không viết [xxx] hay ngoặc vuông cho nội dung khác. Giới hạn ~4000 ký tự."
)

MAX_RETRIES = 2

# Lịch sử hội thoại theo user (để bot nhớ chủ đề khi nhắc tiếp) – lưu tối đa N lượt
_CHAT_HISTORY_MAX_TURNS = 10
_user_chat_history: dict[int, deque] = {}
_history_lock = asyncio.Lock()


async def ask_gemini(prompt: str, system: str = SYSTEM_PROMPT, user_id: int | None = None) -> str:
    """Gửi câu hỏi tới Grok (xAI) và nhận phản hồi. Nếu user_id có giá trị thì gửi kèm lịch sử gần nhất để AI nhớ ngữ cảnh."""
    if not grok_client:
        return f"{E_CROSS} AI chưa được cấu hình. Vui lòng thêm AI_API_KEY (xAI) vào config."

    messages = [{"role": "system", "content": system}]
    if user_id is not None:
        async with _history_lock:
            history = _user_chat_history.get(user_id)
            if history:
                for u, a in history:
                    messages.append({"role": "user", "content": u})
                    messages.append({"role": "assistant", "content": a})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(MAX_RETRIES + 1):
        try:
            completion = await grok_client.chat.completions.create(
                model=GROK_MODEL,
                messages=messages,
            )
            if completion.choices and completion.choices[0].message.content:
                text = completion.choices[0].message.content
                out = _apply_emoji_placeholders(text)
                if user_id is not None and not out.startswith((E_CROSS, E_WAIT, E_WARN)):
                    async with _history_lock:
                        if user_id not in _user_chat_history:
                            # Chủ bot (SUDO): lưu không giới hạn lượt; user khác: tối đa N lượt
                            _user_chat_history[user_id] = (
                                deque() if user_id in SUDO else deque(maxlen=_CHAT_HISTORY_MAX_TURNS)
                            )
                        _user_chat_history[user_id].append((prompt, out))
                return out
            return f"{E_WARN} AI không thể tạo phản hồi. Vui lòng thử lại."
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str or "429" in error_str or "resource" in error_str:
                if attempt < MAX_RETRIES:
                    LOGGER.warning("Grok rate limit, retrying in 10s (attempt %s/%s)", attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(10)
                    continue
                return f"{E_WAIT} AI đang bận, vui lòng thử lại sau ít phút nhé! (Đã hết quota tạm thời)"
            LOGGER.error("Grok API error: %s", e)
            return f"{E_CROSS} Lỗi AI: {str(e)}"
    return f"{E_WAIT} AI đang bận, vui lòng thử lại sau ít phút nhé!"


@app.on_message(filters.command(["ai", "ask"], COMMAND_HANDLER))
@capture_err
async def ai_chat(client: Client, message: Message):
    """Xử lý lệnh /ai và /ask - Hỏi đáp với AI."""
    # Lấy câu hỏi từ text hoặc reply
    if len(message.command) > 1:
        question = message.text.split(None, 1)[1]
    elif message.reply_to_message and (
        message.reply_to_message.text or message.reply_to_message.caption
    ):
        question = message.reply_to_message.text or message.reply_to_message.caption
    else:
        return await message.reply(
            f"{E_BOT} <b>Trợ lý AI – DoraSuper</b>\n\n"
            "Sử dụng: <code>/ai [câu hỏi]</code>\n"
            "Hoặc trả lời một tin nhắn với <code>/ai</code>",
            quote=True,
            parse_mode=ParseMode.HTML,
        )

    # Hiển thị trạng thái đang xử lý
    wait_msg = await message.reply(f"{E_PENDING} Hmmmmm{E_TYMMY}! Đợi em chút xíu nha{E_LOADING}", quote=True, parse_mode=ParseMode.HTML)

    # Gọi Grok API (có gửi lịch sử theo user_id để bot nhớ chủ đề khi nhắc tiếp)
    user_name = message.from_user.first_name if message.from_user else "Người dùng"
    prompt = f"[{user_name}]: {question}"
    user_id = message.from_user.id if message.from_user else None
    answer = await ask_gemini(prompt, user_id=user_id)

    # Chuyển **tên** (Markdown) thành <b>tên</b>; trong mọi *...* thay cắn môi/nháy mắt/mỉm cười   bằng emoji
    safe_name = html.escape(user_name)
    answer = re.sub(r"\*\*" + re.escape(user_name) + r"\*\*", f"<b>{safe_name}</b>", answer)
    answer = re.sub(r"\*\*DoraSuper\*\*", "<b>DoraSuper</b>", answer)

    def _actions_to_emoji(m):
        inner = m.group(1)
        inner = inner.replace("mỉm cười  ", E_SIDEWAYS).replace("nháy mắt", E_WINK).replace("cắn môi", E_BITE_YOUR_LIPS)
        return inner.strip()
    answer = re.sub(r"\*([^*]+)\*", _actions_to_emoji, answer)

    # Format kết quả
    result = f"{E_BOT} <b>DoraSuper AI</b>\nHỏi bởi: <b>{safe_name}</b>\n\n{answer}"

    # Lưu log đối thoại để huấn luyện AI (không chặn gửi tin)
    asyncio.create_task(
        _append_chat_log(
            question,
            answer,
            command="ai",
            user_id=message.from_user.id if message.from_user else None,
        )
    )

    try:
        await wait_msg.edit(result, parse_mode=ParseMode.HTML)
    except MessageTooLong:
        url = await rentry(answer)
        await wait_msg.edit(
            f"{E_BOT} <b>Câu trả lời quá dài, đã dán vào Rentry:</b>\n{url}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        # Thử gửi không parse mode nếu markdown bị lỗi
        try:
            await wait_msg.edit(result, parse_mode=ParseMode.DISABLED)
        except MessageTooLong:
            url = await rentry(answer)
            await wait_msg.edit(
                f"{E_BOT} Câu trả lời quá dài, đã dán vào Rentry:\n{url}",
                parse_mode=ParseMode.DISABLED,
            )


@app.on_message(filters.command(["summarize", "tomtat"], COMMAND_HANDLER))
@capture_err
async def ai_summarize(client: Client, message: Message):
    """Tóm tắt nội dung tin nhắn bằng AI."""
    if not message.reply_to_message:
        return await message.reply(
            f"{E_NOTE} Trả lời một tin nhắn dài để AI tóm tắt nội dung.\n"
            "Sử dụng: Trả lời tin nhắn + <code>/summarize</code>",
            quote=True,
        )

    text = message.reply_to_message.text or message.reply_to_message.caption
    if not text:
        return await message.reply(f"{E_WARN} Tin nhắn được trả lời không có văn bản.", quote=True, parse_mode=ParseMode.HTML)

    wait_msg = await message.reply(f"{E_NOTE} Đang tóm tắt...", quote=True, parse_mode=ParseMode.HTML)

    summary_prompt = (
        "Hãy tóm tắt nội dung sau đây một cách ngắn gọn, rõ ràng, "
        "giữ lại các ý chính quan trọng nhất:\n\n"
        f"{text}"
    )
    answer = await ask_gemini(summary_prompt)
    result = f"{E_NOTE} <b>Tóm tắt bởi AI</b>\n\n{answer}"

    asyncio.create_task(
        _append_chat_log(
            summary_prompt,
            answer,
            command="summarize",
            user_id=message.from_user.id if message.from_user else None,
        )
    )

    try:
        await wait_msg.edit(result, parse_mode=ParseMode.HTML)
    except MessageTooLong:
        url = await rentry(answer)
        await wait_msg.edit(f"{E_NOTE} <b>Tóm tắt quá dài, đã dán vào Rentry:</b>\n{url}", parse_mode=ParseMode.HTML)
    except Exception:
        await wait_msg.edit(result, parse_mode=ParseMode.DISABLED)


@app.on_message(filters.command(["rewrite", "vietlai"], COMMAND_HANDLER))
@capture_err
async def ai_rewrite(client: Client, message: Message):
    """Viết lại văn bản cho hay hơn bằng AI."""
    if len(message.command) > 1:
        text = message.text.split(None, 1)[1]
    elif message.reply_to_message and (
        message.reply_to_message.text or message.reply_to_message.caption
    ):
        text = message.reply_to_message.text or message.reply_to_message.caption
    else:
        return await message.reply(
            f"{E_LOADING} Nhập văn bản hoặc trả lời tin nhắn để AI viết lại.\n"
            "Sử dụng: <code>/rewrite [văn bản]</code>",
            quote=True,
            parse_mode=ParseMode.HTML,
        )

    wait_msg = await message.reply(f"{E_LOADING} Đang viết lại...", quote=True, parse_mode=ParseMode.HTML)

    rewrite_prompt = (
        "Hãy viết lại đoạn văn bản sau cho hay hơn, mạch lạc hơn, "
        "giữ nguyên ý nghĩa gốc nhưng cải thiện cách diễn đạt:\n\n"
        f"{text}"
    )
    answer = await ask_gemini(rewrite_prompt)
    result = f"{E_LOADING} <b>Văn bản đã viết lại</b>\n\n{answer}"

    asyncio.create_task(
        _append_chat_log(
            rewrite_prompt,
            answer,
            command="rewrite",
            user_id=message.from_user.id if message.from_user else None,
        )
    )

    try:
        await wait_msg.edit(result, parse_mode=ParseMode.HTML)
    except MessageTooLong:
        url = await rentry(answer)
        await wait_msg.edit(f"{E_LOADING} <b>Văn bản quá dài, đã dán vào Rentry:</b>\n{url}", parse_mode=ParseMode.HTML)
    except Exception:
        await wait_msg.edit(result, parse_mode=ParseMode.DISABLED)
