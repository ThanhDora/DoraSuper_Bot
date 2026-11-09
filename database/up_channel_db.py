import time
from database import dbname

_col = dbname["up_channel"]
_files = dbname["up_files"]
_users = dbname["up_users"]
_bans = dbname["up_leave_bans"]
_KEY = "default"


async def get_up_channel():
    doc = await _col.find_one({"_id": _KEY})
    if not doc:
        return None
    return doc.get("chat_id")


async def set_up_channel(chat_id):
    await _col.update_one(
        {"_id": _KEY},
        {"$set": {"chat_id": chat_id}},
        upsert=True,
    )
    return chat_id


async def get_up_promo_links():
    """Trả (link_channel, link_group); mỗi cái là URL https hoặc None."""
    targets = await get_up_promo_targets()
    return targets["channel"]["url"], targets["group"]["url"]


async def get_up_promo_targets():
    """Trả {channel:{url,chat_id}, group:{url,chat_id}}."""
    doc = await _col.find_one({"_id": _KEY}) or {}
    def _one(prefix):
        url = (doc.get(f"link_{prefix}") or "").strip() or None
        cid = doc.get(f"link_{prefix}_chat_id")
        try:
            cid = int(cid) if cid is not None else None
        except (TypeError, ValueError):
            cid = None
        return {"url": url, "chat_id": cid}
    return {"channel": _one("channel"), "group": _one("group")}


async def set_up_link_channel(url, chat_id=None):
    if not url:
        await _col.update_one(
            {"_id": _KEY},
            {"$unset": {"link_channel": "", "link_channel_chat_id": ""}},
            upsert=True,
        )
        return None
    payload = {"link_channel": url}
    if chat_id is not None:
        payload["link_channel_chat_id"] = int(chat_id)
    await _col.update_one({"_id": _KEY}, {"$set": payload}, upsert=True)
    return url


async def set_up_link_group(url, chat_id=None):
    if not url:
        await _col.update_one(
            {"_id": _KEY},
            {"$unset": {"link_group": "", "link_group_chat_id": ""}},
            upsert=True,
        )
        return None
    payload = {"link_group": url}
    if chat_id is not None:
        payload["link_group_chat_id"] = int(chat_id)
    await _col.update_one({"_id": _KEY}, {"$set": payload}, upsert=True)
    return url


async def save_up_file(token: str, data: dict):
    payload = dict(data)
    payload["_id"] = token
    await _files.update_one({"_id": token}, {"$set": payload}, upsert=True)
    return token


async def get_up_file(token: str):
    if not token:
        return None
    return await _files.find_one({"_id": token})


async def get_up_acl(user_id: int):
    if user_id is None:
        return None
    return await _users.find_one({"_id": int(user_id)})


async def is_up_allowed(user_id: int) -> bool:
    doc = await get_up_acl(user_id)
    return bool(doc and doc.get("status") == "allowed")


async def set_up_acl(user_id: int, status: str, **meta):
    payload = {"status": status, **meta}
    await _users.update_one({"_id": int(user_id)}, {"$set": payload}, upsert=True)
    return payload


async def save_leave_ban(user_id: int, data: dict):
    payload = dict(data)
    payload["_id"] = int(user_id)
    payload["user_id"] = int(user_id)
    await _bans.update_one({"_id": int(user_id)}, {"$set": payload}, upsert=True)
    return payload


async def get_leave_ban(user_id: int):
    if user_id is None:
        return None
    return await _bans.find_one({"_id": int(user_id)})


async def clear_leave_ban(user_id: int):
    if user_id is None:
        return
    await _bans.delete_one({"_id": int(user_id)})


async def list_leave_bans(limit: int = 50):
    lim = max(1, int(limit))
    cursor = _bans.find().sort([("banned_at", -1)]).limit(lim)
    return await cursor.to_list(length=lim)


async def list_up_acl(status: str | None = "allowed", limit: int = 100):
    """Liệt kê ACL /up theo status (allowed|pending|denied|revoked|None=all)."""
    lim = max(1, int(limit))
    query = {}
    if status:
        query["status"] = status
    # decided_at / requested_at may be missing on old docs
    cursor = _users.find(query).sort([("decided_at", -1), ("requested_at", -1)]).limit(lim)
    return await cursor.to_list(length=lim)


async def clear_up_acl(user_id: int):
    """Xóa hẳn record ACL (hiếm dùng)."""
    if user_id is None:
        return
    await _users.delete_one({"_id": int(user_id)})


async def revoke_up_acl(user_id: int, *, by: int | None = None):
    """Gỡ quyền /up: status=revoked (chạy /up lại sẽ xin duyệt mới)."""
    payload = {"status": "revoked", "revoked_at": time.time()}
    if by is not None:
        payload["revoked_by"] = int(by)
    await _users.update_one({"_id": int(user_id)}, {"$set": payload}, upsert=False)
    return payload
