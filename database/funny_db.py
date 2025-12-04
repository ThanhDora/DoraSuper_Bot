from typing import Dict, Union
from datetime import datetime, timedelta
from database import dbname

funnydb = dbname["funny"]

async def get_user_command_usage(chat_id: int, user_id: int, command: str) -> Union[dict, bool]:
    """Kiểm tra lần sử dụng gần nhất của người dùng với lệnh cụ thể."""
    usage = await funnydb.find_one({"chat_id": chat_id, "user_id": user_id, "command": command})
    return usage if usage else False

async def update_user_command_usage(chat_id: int, user_id: int, command: str):
    """Cập nhật hoặc ghi lại lần sử dụng lệnh của người dùng."""
    usage_data = {
        "chat_id": chat_id,
        "user_id": user_id,
        "command": command,
        "last_used": datetime.utcnow()
    }
    await funnydb.update_one(
        {"chat_id": chat_id, "user_id": user_id, "command": command},
        {"$set": usage_data},
        upsert=True
    )

async def can_use_command(chat_id: int, user_id: int, command: str) -> bool:
    """Kiểm tra xem người dùng có thể sử dụng lệnh hay không (chưa dùng trong ngày)."""
    usage = await get_user_command_usage(chat_id, user_id, command)
    if not usage:
        return True
    last_used = usage["last_used"]
    # Kiểm tra xem đã qua 24 giờ chưa
    if datetime.utcnow() - last_used >= timedelta(days=1):
        return True
    return False

async def reset_user_command_usage(chat_id: int, user_id: int):
    """Xóa dữ liệu sử dụng lệnh của người dùng trong chat cụ thể."""
    await funnydb.delete_many({"chat_id": chat_id, "user_id": user_id})