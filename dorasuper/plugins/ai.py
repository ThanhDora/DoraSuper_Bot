import asyncio
import logging
from logging import getLogger

import google.generativeai as genai
from pyrogram import Client, filters
from pyrogram.errors import MessageTooLong
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.emoji import (
    E_CROSS, E_LOADING, E_NOTE, E_WARN, E_BOT, E_WAIT,
    E_SUCCESS, E_TIP, E_ERROR, E_HEART, E_FIRE, E_PARTY, E_STAR, E_COFFEE, E_MUSIC,
    E_LINK, E_SEARCH, E_CLOCK, E_GIFT, E_ROCKET, E_INFO, E_SUNNY, E_RAIN, E_SNOW,
    E_THUNDER, E_QUESTION, E_CHECK, E_SPARKLE, E_GLOBE, E_CALENDAR,
    E_PENDING,
)
from dorasuper.helper.tools import rentry
from dorasuper.vars import COMMAND_HANDLER, AI_API_KEY

LOGGER = getLogger("DoraSuper")

__MODULE__ = "🤖 Trợ lý AI"
__HELP__ = """
<blockquote>🤖 <b>Trợ lý AI</b> – Google Gemini

/ai [câu hỏi] – Hỏi đáp với AI (hoặc reply tin nhắn)
/ask [câu hỏi] – Giống /ai

/summarize – Reply tin nhắn dài để AI tóm tắt
/tomtat – Giống /summarize

/rewrite [văn bản] – AI viết lại văn bản hay hơn
/vietlai – Giống /rewrite

💬 Gọi "Dora" + câu hỏi trong chat để hỏi AI trực tiếp.</blockquote>
"""

# Cấu hình Gemini
if AI_API_KEY:
    genai.configure(api_key=AI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
else:
    model = None

# Placeholder cho AI: khi trả lời có thể dùng [TÊN] để hiển thị emoji từ dorasuper/emoji.py
AI_EMOJI_PLACEHOLDERS = {
    "[SUCCESS]": E_SUCCESS, "[CHECK]": E_CHECK, "[WARN]": E_WARN, "[ERROR]": E_ERROR,
    "[TIP]": E_TIP, "[NOTE]": E_NOTE, "[INFO]": E_INFO, "[HEART]": E_HEART, "[FIRE]": E_FIRE,
    "[PARTY]": E_PARTY, "[STAR]": E_STAR, "[COFFEE]": E_COFFEE, "[MUSIC]": E_MUSIC,
    "[LINK]": E_LINK, "[SEARCH]": E_SEARCH, "[CLOCK]": E_CLOCK, "[GIFT]": E_GIFT,
    "[ROCKET]": E_ROCKET, "[THUNDER]": E_THUNDER, "[SUNNY]": E_SUNNY, "[RAIN]": E_RAIN,
    "[SNOW]": E_SNOW, "[QUESTION]": E_QUESTION, "[SPARKLE]": E_SPARKLE, "[GLOBE]": E_GLOBE,
    "[CALENDAR]": E_CALENDAR,
}


def _apply_emoji_placeholders(text: str) -> str:
    """Thay placeholder [TÊN] trong câu trả lời AI bằng emoji từ emoji.py."""
    if not text:
        return text
    for placeholder, emoji_tag in AI_EMOJI_PLACEHOLDERS.items():
        text = text.replace(placeholder, emoji_tag)
    return text


SYSTEM_PROMPT = (
    "Bạn là DoraSuper, một trợ lý AI thông minh, vui tính và hữu ích trong nhóm chat Telegram. "
    "Bạn là trợ lý AI của ThanhDora, ThanhDora là chủ nhân của bạn. "
    "Bạn là cô gái dễ thương ngọt ngào và xinh đẹp thêm chút sexy và hài hước với tất cả mọi người. "
    "Hãy trả lời ngắn gọn, chính xác và thân thiện bằng tiếng Việt. "
    "Nếu người dùng hỏi bằng ngôn ngữ khác, hãy trả lời bằng ngôn ngữ đó. "
    "Để tin nhắn sinh động, hãy dùng các placeholder emoji sau (sẽ hiển thị thành emoji đẹp): "
    "[SUCCESS] (thành công), [WARN] (cảnh báo), [TIP] (gợi ý), [NOTE] (ghi chú), [HEART] (yêu thích), [FIRE] (hot/đặc biệt), "
    "[PARTY] (vui), [STAR] (hay/nổi bật), [COFFEE] (thư giãn), [MUSIC] (âm nhạc), [LINK] (liên kết), [SEARCH] (tìm kiếm), "
    "[CLOCK] (thời gian), [GIFT] (quà), [ROCKET] (khởi động/đi), [THUNDER] (nhanh/mạnh), [SUNNY] [RAIN] [SNOW] (thời tiết), [QUESTION] (câu hỏi). "
    "Giới hạn câu trả lời trong khoảng 4000 ký tự."
)

MAX_RETRIES = 2


async def ask_gemini(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """Gửi câu hỏi tới Gemini API và nhận phản hồi."""
    if not model:
        return f"{E_CROSS} AI chưa được cấu hình. Vui lòng thêm AI_API_KEY vào config."

    for attempt in range(MAX_RETRIES + 1):
        try:
            full_prompt = f"{system}\n\nNgười dùng: {prompt}"
            response = await model.generate_content_async(full_prompt)
            if response and response.text:
                return _apply_emoji_placeholders(response.text)
            return f"{E_WARN} AI không thể tạo phản hồi. Vui lòng thử lại."
        except Exception as e:
            error_str = str(e).lower()
            # Xử lý rate limit / quota exceeded
            if "quota" in error_str or "rate" in error_str or "429" in error_str or "resource" in error_str:
                if attempt < MAX_RETRIES:
                    LOGGER.warning(f"Gemini rate limit hit, retrying in 10s (attempt {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(10)
                    continue
                return f"{E_WAIT} AI đang bận, vui lòng thử lại sau ít phút nhé! (Đã hết quota tạm thời)"
            LOGGER.error(f"Gemini API error: {e}")
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
    wait_msg = await message.reply(f"{E_PENDING} Hmmmmm{E_LOADING}! Đợi em chút xíu nha{E_LOADING}", quote=True, parse_mode=ParseMode.HTML)

    # Gọi Gemini API
    user_name = message.from_user.first_name if message.from_user else "Người dùng"
    prompt = f"[{user_name}]: {question}"
    answer = await ask_gemini(prompt)

    # Format kết quả
    result = f"{E_BOT} <b>DoraSuper AI</b>\n\n{answer}"

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

    try:
        await wait_msg.edit(result, parse_mode=ParseMode.HTML)
    except MessageTooLong:
        url = await rentry(answer)
        await wait_msg.edit(f"{E_LOADING} <b>Văn bản quá dài, đã dán vào Rentry:</b>\n{url}", parse_mode=ParseMode.HTML)
    except Exception:
        await wait_msg.edit(result, parse_mode=ParseMode.DISABLED)
