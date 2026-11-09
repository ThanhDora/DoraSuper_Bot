from database import dbname

_col = dbname["up_channel"]
_files = dbname["up_files"]
_users = dbname["up_users"]
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
    doc = await _col.find_one({"_id": _KEY})
    if not doc:
        return None, None
    channel = (doc.get("link_channel") or "").strip() or None
    group = (doc.get("link_group") or "").strip() or None
    return channel, group


async def set_up_link_channel(url):
    if url:
        await _col.update_one(
            {"_id": _KEY}, {"$set": {"link_channel": url}}, upsert=True,
        )
    else:
        await _col.update_one(
            {"_id": _KEY}, {"$unset": {"link_channel": ""}}, upsert=True,
        )
    return url


async def set_up_link_group(url):
    if url:
        await _col.update_one(
            {"_id": _KEY}, {"$set": {"link_group": url}}, upsert=True,
        )
    else:
        await _col.update_one(
            {"_id": _KEY}, {"$unset": {"link_group": ""}}, upsert=True,
        )
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
