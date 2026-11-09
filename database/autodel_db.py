from database import dbname

_settings = dbname["autodel_settings"]
_pending = dbname["autodel_pending"]
_KEY = "global"
_DEFAULT_SECONDS = 60


async def get_autodel_settings() -> dict:
    doc = await _settings.find_one({"_id": _KEY}) or {}
    enabled = doc.get("enabled")
    if enabled is None:
        enabled = True
    seconds = doc.get("seconds")
    try:
        seconds = int(seconds) if seconds is not None else _DEFAULT_SECONDS
    except (TypeError, ValueError):
        seconds = _DEFAULT_SECONDS
    seconds = max(5, min(86400, seconds))
    return {"enabled": bool(enabled), "seconds": seconds}


async def set_autodel_enabled(enabled: bool):
    await _settings.update_one(
        {"_id": _KEY}, {"$set": {"enabled": bool(enabled)}}, upsert=True,
    )
    return await get_autodel_settings()


async def set_autodel_seconds(seconds: int):
    seconds = max(5, min(86400, int(seconds)))
    await _settings.update_one(
        {"_id": _KEY},
        {"$set": {"seconds": seconds, "enabled": True}},
        upsert=True,
    )
    return await get_autodel_settings()


async def add_pending_delete(chat_id: int, message_id: int, delete_at: float, user_message_id=None):
    await _pending.update_one(
        {"chat_id": int(chat_id), "message_id": int(message_id)},
        {"$set": {
            "chat_id": int(chat_id),
            "message_id": int(message_id),
            "delete_at": float(delete_at),
            "user_message_id": int(user_message_id) if user_message_id else None,
        }},
        upsert=True,
    )


async def remove_pending_delete(chat_id: int, message_id: int):
    await _pending.delete_one({"chat_id": int(chat_id), "message_id": int(message_id)})


async def list_pending_deletes(limit: int = 500):
    lim = max(1, int(limit))
    cursor = _pending.find().sort([("delete_at", 1)]).limit(lim)
    return await cursor.to_list(length=lim)
