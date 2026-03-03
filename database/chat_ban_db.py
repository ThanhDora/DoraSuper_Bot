# Lưu danh sách user bị cấm theo từng nhóm (để tự động cấm lại khi họ được mời vào lại)

from time import time

from database import dbname

chat_ban_coll = dbname["chat_bans"]


async def add_chat_ban(chat_id: int, user_id: int, until_ts: int = 0) -> None:
    """Thêm user vào danh sách cấm: until_ts=0 = cấm vĩnh viễn, until_ts>0 = cấm đến timestamp (tcam)."""
    await chat_ban_coll.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"chat_id": chat_id, "user_id": user_id, "until_ts": until_ts}},
        upsert=True,
    )


async def remove_chat_ban(chat_id: int, user_id: int) -> None:
    """Xóa user khỏi danh sách cấm của nhóm."""
    await chat_ban_coll.delete_one({"chat_id": chat_id, "user_id": user_id})


async def is_chat_banned(chat_id: int, user_id: int) -> bool:
    """Kiểm tra user có đang bị cấm (chưa hết hạn) trong nhóm không."""
    return await get_chat_ban_until(chat_id, user_id) is not None


async def get_chat_ban_until(chat_id: int, user_id: int) -> int | None:
    """Trả về until_ts: None = không cấm hoặc đã hết hạn, 0 = cấm vĩnh viễn, >0 = cấm đến timestamp."""
    doc = await chat_ban_coll.find_one({"chat_id": chat_id, "user_id": user_id})
    if not doc:
        return None
    until_ts = doc.get("until_ts", 0)
    if until_ts > 0 and time() >= until_ts:
        await chat_ban_coll.delete_one({"chat_id": chat_id, "user_id": user_id})
        return None
    return until_ts
