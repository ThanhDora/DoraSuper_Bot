from database import dbname

greetingdb = dbname["greetings"]

# Chức năng chào mừng
async def is_welcome(chat_id: int) -> bool:
    data = await greetingdb.find_one({"chat_id": chat_id})
    return bool(data and data.get("welcome_enabled", False))

async def toggle_welcome(chat_id: int):
    data = await greetingdb.find_one({"chat_id": chat_id})
    if data and data.get("welcome_enabled", False):
        await greetingdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"welcome_enabled": False}}
        )
        return False
    else:
        await greetingdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"welcome_enabled": True}},
            upsert=True
        )
        return True

async def set_custom_welcome(chat_id: int, custom_message: str, buttons: list = None):
    await greetingdb.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "welcome_enabled": True,
            "custom_welcome_message": custom_message,
            "welcome_buttons": buttons or []
        }},
        upsert=True
    )

async def get_custom_welcome(chat_id: int):
    data = await greetingdb.find_one({"chat_id": chat_id})
    if data and "custom_welcome_message" in data:
        return data["custom_welcome_message"], data.get("welcome_buttons", [])
    return None, []

# Chức năng cấm tự động khi rời nhóm
async def is_ban_on_leave(chat_id: int) -> bool:
    data = await greetingdb.find_one({"chat_id": chat_id})
    return bool(data and data.get("ban_on_leave_enabled", False))

async def toggle_ban_on_leave(chat_id: int):
    data = await greetingdb.find_one({"chat_id": chat_id})
    if data and data.get("ban_on_leave_enabled", False):
        await greetingdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"ban_on_leave_enabled": False}}
        )
        return False
    else:
        await greetingdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"ban_on_leave_enabled": True}},
            upsert=True
        )
        return True