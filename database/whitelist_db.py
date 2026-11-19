"""Mongo helpers for per-chat and global whitelist."""
from time import time

from database import dbname
from dorasuper.helper.whitelist import GLOBAL_CHAT_ID

whitelistdb = dbname["whitelist"]


async def add_whitelist(chat_id: int, user_id: int, added_by: int = 0, name: str = "") -> bool:
    """Add user to whitelist. Returns True if newly inserted."""
    chat_id = int(chat_id)
    user_id = int(user_id)
    existing = await whitelistdb.find_one({"chat_id": chat_id, "user_id": user_id})
    if existing:
        return False
    await whitelistdb.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {
            "$set": {
                "chat_id": chat_id,
                "user_id": user_id,
                "added_by": int(added_by or 0),
                "name": name or "",
                "added_at": time(),
            }
        },
        upsert=True,
    )
    return True


async def remove_whitelist(chat_id: int, user_id: int) -> bool:
    res = await whitelistdb.delete_one({"chat_id": int(chat_id), "user_id": int(user_id)})
    return bool(getattr(res, "deleted_count", 0))


async def list_whitelist(chat_id: int) -> list:
    cursor = whitelistdb.find({"chat_id": int(chat_id)})
    return await cursor.to_list(length=2000)


async def is_whitelisted(chat_id: int, user_id: int) -> bool:
    if not user_id:
        return False
    try:
        user_id = int(user_id)
        chat_id = int(chat_id)
    except (TypeError, ValueError):
        return False
    doc = await whitelistdb.find_one(
        {"user_id": user_id, "chat_id": {"$in": [chat_id, GLOBAL_CHAT_ID]}}
    )
    return bool(doc)


async def is_globally_whitelisted(user_id: int) -> bool:
    if not user_id:
        return False
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return False
    doc = await whitelistdb.find_one({"chat_id": GLOBAL_CHAT_ID, "user_id": user_id})
    return bool(doc)


async def add_global_whitelist(user_id: int, added_by: int = 0, name: str = "") -> bool:
    return await add_whitelist(GLOBAL_CHAT_ID, user_id, added_by=added_by, name=name)


async def remove_global_whitelist(user_id: int) -> bool:
    return await remove_whitelist(GLOBAL_CHAT_ID, user_id)


async def list_global_whitelist() -> list:
    return await list_whitelist(GLOBAL_CHAT_ID)
