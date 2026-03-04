from database import dbname

# Collection riêng cho AFK, tránh xung đột với bất kỳ code nào dùng "users"
afkdb = dbname["afk"]
cleandb = dbname["cleanmode"]
cleanmode = {}


async def is_cleanmode_on(chat_id: int) -> bool:
    mode = cleanmode.get(chat_id)
    if not mode:
        user = await cleandb.find_one({"chat_id": chat_id})
        if not user:
            cleanmode[chat_id] = True
            return True
        cleanmode[chat_id] = False
        return False
    return mode


async def cleanmode_on(chat_id: int):
    cleanmode[chat_id] = True
    user = await cleandb.find_one({"chat_id": chat_id})
    if user:
        return await cleandb.delete_one({"chat_id": chat_id})


async def cleanmode_off(chat_id: int):
    cleanmode[chat_id] = False
    user = await cleandb.find_one({"chat_id": chat_id})
    if not user:
        return await cleandb.insert_one({"chat_id": chat_id})


async def is_afk(user_id: int) -> bool:
    user = await afkdb.find_one({"user_id": user_id})
    if user and "reason" in user:
        return (True, user["reason"])
    return (False, {})


async def add_afk(user_id: int, mode):
    await afkdb.update_one(
        {"user_id": user_id}, {"$set": {"reason": mode}}, upsert=True
    )


async def remove_afk(user_id: int):
    """Xóa trạng thái AFK của user. Dùng delete_many để chắc chắn xóa hết nếu có trùng."""
    result = await afkdb.delete_many({"user_id": user_id})
    return result


async def get_afk_users() -> list:
    users = afkdb.find({"user_id": {"$gt": 0}})
    return list(await users.to_list(length=1000000000)) if users else []
