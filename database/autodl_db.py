# Bật/tắt tự động tải video/ảnh từ link theo từng chat (nhóm hoặc riêng tư)

from database import dbname

autodl_coll = dbname["autodl"]


async def is_autodl_on(chat_id: int) -> bool:
    """Mặc định True (bật) cho nhóm chưa cấu hình. Admin dùng /autodl để tắt."""
    doc = await autodl_coll.find_one({"chat_id": chat_id})
    if doc is None:
        return True
    return bool(doc.get("enabled", True))


async def set_autodl(chat_id: int, enabled: bool):
    await autodl_coll.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": enabled}},
        upsert=True,
    )


async def toggle_autodl(chat_id: int) -> bool:
    """Bật nếu đang tắt, tắt nếu đang bật. Trả về trạng thái sau khi đổi."""
    current = await is_autodl_on(chat_id)
    new = not current
    await set_autodl(chat_id, new)
    return new
