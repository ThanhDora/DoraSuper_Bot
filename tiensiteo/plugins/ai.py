import asyncio
import logging
from logging import getLogger

import google.generativeai as genai
from pyrogram import Client, filters
from pyrogram.errors import MessageTooLong
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.helper.tools import rentry
from tiensiteo.vars import COMMAND_HANDLER, AI_API_KEY

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "TrợLýAI"
__HELP__ = """
<blockquote>🤖 Tính năng Trợ lý AI sử dụng Google Gemini

/ai [câu hỏi] - Hỏi đáp với AI (hoặc trả lời một tin nhắn)

/ask [câu hỏi] - Tương tự /ai

/summarize - Trả lời một tin nhắn dài để AI tóm tắt nội dung

/rewrite [văn bản] - AI viết lại văn bản cho hay hơn

Hoặc gọi tên "Tèo" kèm câu hỏi để hỏi AI trực tiếp!</blockquote>
"""

# Cấu hình Gemini
if AI_API_KEY:
    genai.configure(api_key=AI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
else:
    model = None

SYSTEM_PROMPT = (
    "Bạn là Tiến sĩ Tèo, một trợ lý AI thông minh, vui tính và hữu ích trong nhóm chat Telegram. "
    "Hãy trả lời ngắn gọn, chính xác và thân thiện bằng tiếng Việt. "
    "Nếu người dùng hỏi bằng ngôn ngữ khác, hãy trả lời bằng ngôn ngữ đó. "
    "Sử dụng emoji phù hợp để tin nhắn sinh động hơn. "
    "Giới hạn câu trả lời trong khoảng 4000 ký tự."
)

MAX_RETRIES = 2


async def ask_gemini(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """Gửi câu hỏi tới Gemini API và nhận phản hồi."""
    if not model:
        return "❌ AI chưa được cấu hình. Vui lòng thêm AI_API_KEY vào config."

    for attempt in range(MAX_RETRIES + 1):
        try:
            full_prompt = f"{system}\n\nNgười dùng: {prompt}"
            response = await model.generate_content_async(full_prompt)
            if response and response.text:
                return response.text
            return "⚠️ AI không thể tạo phản hồi. Vui lòng thử lại."
        except Exception as e:
            error_str = str(e).lower()
            # Xử lý rate limit / quota exceeded
            if "quota" in error_str or "rate" in error_str or "429" in error_str or "resource" in error_str:
                if attempt < MAX_RETRIES:
                    LOGGER.warning(f"Gemini rate limit hit, retrying in 10s (attempt {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(10)
                    continue
                return "⏳ AI đang bận, vui lòng thử lại sau ít phút nhé! (Đã hết quota tạm thời)"
            LOGGER.error(f"Gemini API error: {e}")
            return f"❌ Lỗi AI: {str(e)}"
    return "⏳ AI đang bận, vui lòng thử lại sau ít phút nhé!"


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
            "🤖 <b>Trợ lý AI - Tiến sĩ Tèo</b>\n\n"
            "Sử dụng: <code>/ai [câu hỏi]</code>\n"
            "Hoặc trả lời một tin nhắn với <code>/ai</code>",
            quote=True,
        )

    # Hiển thị trạng thái đang xử lý
    wait_msg = await message.reply("🧠 Đang suy nghĩ...", quote=True)

    # Gọi Gemini API
    user_name = message.from_user.first_name if message.from_user else "Người dùng"
    prompt = f"[{user_name}]: {question}"
    answer = await ask_gemini(prompt)

    # Format kết quả
    result = f"🤖 <b>Tiến sĩ Tèo AI</b>\n\n{answer}"

    try:
        await wait_msg.edit(result)
    except MessageTooLong:
        url = await rentry(answer)
        await wait_msg.edit(
            f"🤖 <b>Câu trả lời quá dài, đã dán vào Rentry:</b>\n{url}"
        )
    except Exception:
        # Thử gửi không parse mode nếu markdown bị lỗi
        try:
            await wait_msg.edit(result, parse_mode=ParseMode.DISABLED)
        except MessageTooLong:
            url = await rentry(answer)
            await wait_msg.edit(
                f"🤖 Câu trả lời quá dài, đã dán vào Rentry:\n{url}",
                parse_mode=ParseMode.DISABLED,
            )


@app.on_message(filters.command(["summarize", "tomtat"], COMMAND_HANDLER))
@capture_err
async def ai_summarize(client: Client, message: Message):
    """Tóm tắt nội dung tin nhắn bằng AI."""
    if not message.reply_to_message:
        return await message.reply(
            "📝 Trả lời một tin nhắn dài để AI tóm tắt nội dung.\n"
            "Sử dụng: Trả lời tin nhắn + <code>/summarize</code>",
            quote=True,
        )

    text = message.reply_to_message.text or message.reply_to_message.caption
    if not text:
        return await message.reply("⚠️ Tin nhắn được trả lời không có văn bản.", quote=True)

    wait_msg = await message.reply("📝 Đang tóm tắt...", quote=True)

    summary_prompt = (
        "Hãy tóm tắt nội dung sau đây một cách ngắn gọn, rõ ràng, "
        "giữ lại các ý chính quan trọng nhất:\n\n"
        f"{text}"
    )
    answer = await ask_gemini(summary_prompt)
    result = f"📝 <b>Tóm tắt bởi AI</b>\n\n{answer}"

    try:
        await wait_msg.edit(result)
    except MessageTooLong:
        url = await rentry(answer)
        await wait_msg.edit(f"📝 <b>Tóm tắt quá dài, đã dán vào Rentry:</b>\n{url}")
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
            "✍️ Nhập văn bản hoặc trả lời tin nhắn để AI viết lại.\n"
            "Sử dụng: <code>/rewrite [văn bản]</code>",
            quote=True,
        )

    wait_msg = await message.reply("✍️ Đang viết lại...", quote=True)

    rewrite_prompt = (
        "Hãy viết lại đoạn văn bản sau cho hay hơn, mạch lạc hơn, "
        "giữ nguyên ý nghĩa gốc nhưng cải thiện cách diễn đạt:\n\n"
        f"{text}"
    )
    answer = await ask_gemini(rewrite_prompt)
    result = f"✍️ <b>Văn bản đã viết lại</b>\n\n{answer}"

    try:
        await wait_msg.edit(result)
    except MessageTooLong:
        url = await rentry(answer)
        await wait_msg.edit(f"✍️ <b>Văn bản quá dài, đã dán vào Rentry:</b>\n{url}")
    except Exception:
        await wait_msg.edit(result, parse_mode=ParseMode.DISABLED)
