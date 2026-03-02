"""
Backend AI: Google Gemini.
Dùng khi AI_PROVIDER=gemini trong config.env. Cần GEMINI_API_KEY.
"""
import asyncio
from logging import getLogger

from dorasuper.emoji import E_CROSS, E_WAIT, E_WARN
from dorasuper.vars import GEMINI_API_KEY

LOGGER = getLogger("DoraSuper")

_gemini_model = None

def _get_model():
    """Khởi tạo model Gemini một lần (lazy)."""
    global _gemini_model
    if _gemini_model is not None:
        return _gemini_model
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel("gemini-2.5-flash-lite")
        return _gemini_model
    except Exception as e:
        LOGGER.warning("Gemini init failed: %s", e)
        return None


MAX_RETRIES = 2


async def ask_gemini_api(prompt: str, system: str) -> str:
    """
    Gửi prompt + system tới Gemini API, trả về nội dung trả lời (raw text)
    hoặc chuỗi lỗi (có E_CROSS/E_WAIT/E_WARN) nếu thất bại.
    """
    model = _get_model()
    if not model:
        return f"{E_CROSS} Gemini chưa được cấu hình. Thêm GEMINI_API_KEY vào config (và đặt AI_PROVIDER=gemini)."

    full_prompt = f"{system}\n\nNgười dùng: {prompt}"
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await model.generate_content_async(full_prompt)
            if response and response.text:
                return response.text
            return f"{E_WARN} Gemini không thể tạo phản hồi. Vui lòng thử lại."
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str or "429" in error_str or "resource" in error_str:
                if attempt < MAX_RETRIES:
                    LOGGER.warning("Gemini rate limit, retrying in 10s (attempt %s/%s)", attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(10)
                    continue
                return f"{E_WAIT} AI đang bận, vui lòng thử lại sau ít phút nhé! (Đã hết quota tạm thời)"
            LOGGER.error("Gemini API error: %s", e)
            return f"{E_CROSS} Lỗi Gemini: {str(e)}"
    return f"{E_WAIT} AI đang bận, vui lòng thử lại sau ít phút nhé!"
