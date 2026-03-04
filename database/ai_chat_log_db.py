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


async def get_recent_chat_history(
    user_id: int,
    limit: int = 10,
) -> list[tuple[str, str]]:
    """Lấy lịch sử trò chuyện gần nhất của user (theo user_id), thứ tự cũ → mới (để gửi vào API theo thời gian).
    Trả về list [(user_content, assistant_content), ...]. Dùng để AI nhớ ngữ cảnh và nhận biết từng người."""
    try:
        cursor = (
            ai_chat_logs.find({"user_id": user_id})
            .sort("timestamp", 1)
            .limit(limit)
        )
        out = []
        async for doc in cursor:
            u = (doc.get("user") or "").strip()
            a = (doc.get("assistant") or "").strip()
            if u or a:
                out.append((u, a))
        return out
    except Exception:
        return []


async def clear_ai_chat_logs() -> int:
    """Xóa toàn bộ bản ghi trong collection ai_chat_logs. Trả về số document đã xóa."""
    result = await ai_chat_logs.delete_many({})
    return result.deleted_count
