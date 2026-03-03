# Lưu user bị tắt mic (mute) theo từng nhóm — khi được mời lại sẽ tự động restrict lại

from time import time

from database import dbname

chat_mute_coll = dbname["chat_mutes"]


async def add_chat_mute(chat_id: int, user_id: int, until_ts: int = 0) -> None:
    """Lưu mute: until_ts=0 = vĩnh viễn (immom), until_ts>0 = hết hạn lúc timestamp (timmom)."""
    await chat_mute_coll.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"chat_id": chat_id, "user_id": user_id, "until_ts": until_ts}},
        upsert=True,
    )


async def remove_chat_mute(chat_id: int, user_id: int) -> None:
    """Xóa user khỏi danh sách mute của nhóm (đã bỏ tắt mic)."""
    await chat_mute_coll.delete_one({"chat_id": chat_id, "user_id": user_id})


async def get_chat_mute_until(chat_id: int, user_id: int) -> int | None:
    """Trả về until_ts nếu user đang bị mute và chưa hết hạn; None nếu không mute hoặc đã hết hạn."""
    doc = await chat_mute_coll.find_one({"chat_id": chat_id, "user_id": user_id})
    if not doc:
        return None
    until_ts = doc.get("until_ts", 0)
    if until_ts > 0 and time() >= until_ts:
        await chat_mute_coll.delete_one({"chat_id": chat_id, "user_id": user_id})
        return None
    return until_ts
