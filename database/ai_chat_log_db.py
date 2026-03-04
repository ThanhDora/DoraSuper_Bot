# Log đối thoại AI (user / assistant) để huấn luyện AI – lưu vào MongoDB

from datetime import datetime, timezone

from database import dbname

ai_chat_logs = dbname["ai_chat_logs"]


async def insert_ai_chat_log(
    user_content: str,
    assistant_content: str,
    command: str = "ai",
    user_id: int | None = None,
) -> None:
    """Thêm một bản ghi đối thoại vào collection ai_chat_logs."""
    if not user_content and not assistant_content:
        return
    doc = {
        "timestamp": datetime.now(timezone.utc),
        "command": command,
        "user_id": user_id,
        "user": (user_content or "").strip()[:10000],
        "assistant": (assistant_content or "").strip()[:10000],
    }
    await ai_chat_logs.insert_one(doc)


async def clear_ai_chat_logs() -> int:
    """Xóa toàn bộ bản ghi trong collection ai_chat_logs. Trả về số document đã xóa."""
    result = await ai_chat_logs.delete_many({})
    return result.deleted_count
