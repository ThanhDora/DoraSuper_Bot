# Lưu danh sách user bị cấm theo từng nhóm (để tự động cấm lại khi họ được mời vào lại)

from database import dbname

chat_ban_coll = dbname["chat_bans"]


async def add_chat_ban(chat_id: int, user_id: int) -> None:
    """Thêm user vào danh sách cấm của nhóm."""
    await chat_ban_coll.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"chat_id": chat_id, "user_id": user_id}},
        upsert=True,
    )


async def remove_chat_ban(chat_id: int, user_id: int) -> None:
    """Xóa user khỏi danh sách cấm của nhóm."""
    await chat_ban_coll.delete_one({"chat_id": chat_id, "user_id": user_id})


async def is_chat_banned(chat_id: int, user_id: int) -> bool:
    """Kiểm tra user có trong danh sách cấm của nhóm không."""
    doc = await chat_ban_coll.find_one({"chat_id": chat_id, "user_id": user_id})
    return doc is not None
