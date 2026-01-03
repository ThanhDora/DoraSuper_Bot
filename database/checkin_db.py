from typing import List, Dict, Optional, Union
from datetime import datetime

from zoneinfo import ZoneInfo
from database import dbname

checkindb = dbname["checkin"]
configdb = dbname["checkin_config"]
usagedb = dbname["checkin_usage"]

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _vn_date(dt_utc: datetime):
    """Lấy date theo giờ Việt Nam từ datetime UTC."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
    return dt_utc.astimezone(VN_TZ).date()


def _vn_ymd_now():
    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    vn = now_utc.astimezone(VN_TZ)
    return vn.year, vn.month, vn.day

async def get_user_command_usage(chat_id: int, user_id: int, command: str) -> Union[dict, bool]:
    usage = await usagedb.find_one({"chat_id": chat_id, "user_id": user_id, "command": command})
    return usage if usage else False


async def update_user_command_usage(chat_id: int, user_id: int, command: str):
    usage_data = {
        "chat_id": chat_id,
        "user_id": user_id,
        "command": command,
        "last_used": datetime.utcnow()
    }
    await usagedb.update_one(
        {"chat_id": chat_id, "user_id": user_id, "command": command},
        {"$set": usage_data},
        upsert=True
    )


async def can_use_command(chat_id: int, user_id: int, command: str) -> bool:
    usage = await get_user_command_usage(chat_id, user_id, command)
    if not usage:
        return True

    last_used = usage.get("last_used")
    if not last_used:
        return True

    last_day_vn = _vn_date(last_used.replace(tzinfo=ZoneInfo("UTC")) if last_used.tzinfo is None else last_used)
    now_day_vn = _vn_date(datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")))
    return now_day_vn != last_day_vn


async def reset_user_command_usage(chat_id: int):
    await usagedb.delete_many({"chat_id": chat_id})


# ----------------------------
# Config chat
# ----------------------------
async def ensure_chat_config(chat_id: int) -> dict:
    cfg = await configdb.find_one({"chat_id": chat_id})
    if cfg:
        return cfg
    now = datetime.utcnow()
    cfg = {"chat_id": chat_id, "enabled": True, "start_date": now, "updated_at": now}
    await configdb.insert_one(cfg)
    return cfg


async def is_checkin_enabled(chat_id: int) -> bool:
    cfg = await ensure_chat_config(chat_id)
    return bool(cfg.get("enabled", True))


async def set_checkin_enabled(chat_id: int, enabled: bool):
    now = datetime.utcnow()
    await configdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": enabled, "updated_at": now}, "$setOnInsert": {"start_date": now}},
        upsert=True
    )


async def get_checkin_start_date(chat_id: int) -> datetime:
    cfg = await ensure_chat_config(chat_id)
    return cfg.get("start_date") or datetime.utcnow()


async def set_checkin_start_date(chat_id: int, start_date: datetime):
    now = datetime.utcnow()
    await configdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"start_date": start_date, "updated_at": now}},
        upsert=True
    )


# ----------------------------
# Log checkin
# ----------------------------
async def log_checkin(chat_id: int, user_id: int, user_name: str) -> datetime:
    """
    Ghi 1 lần điểm danh:
    - ts: UTC
    - y/m/d: theo giờ Việt Nam (để BXH tháng/năm đúng VN)
    """
    ts_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    vn = ts_utc.astimezone(VN_TZ)

    doc = {
        "chat_id": chat_id,
        "user_id": user_id,
        "user_name": user_name,
        "ts": ts_utc.replace(tzinfo=None), 
        "y": vn.year,
        "m": vn.month,
        "d": vn.day,
    }
    await checkindb.insert_one(doc)
    return doc["ts"]


async def get_user_total(chat_id: int, user_id: int, year: Optional[int] = None, month: Optional[int] = None) -> int:
    q: Dict = {"chat_id": chat_id, "user_id": user_id}
    if year is not None:
        q["y"] = year
    if month is not None:
        q["m"] = month
    return await checkindb.count_documents(q)


async def get_top10(chat_id: int, year: Optional[int] = None, month: Optional[int] = None) -> List[dict]:
    q: Dict = {"chat_id": chat_id}
    if year is not None:
        q["y"] = year
    if month is not None:
        q["m"] = month

    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$user_id",
            "count": {"$sum": 1},
            "user_name": {"$last": "$user_name"},
            "last_ts": {"$max": "$ts"},
        }},
        {"$sort": {"count": -1, "last_ts": 1}},
        {"$limit": 10},
    ]
    return await checkindb.aggregate(pipeline).to_list(length=10)


async def reset_checkin(chat_id: int) -> datetime:
    now = datetime.utcnow()
    await checkindb.delete_many({"chat_id": chat_id})
    await reset_user_command_usage(chat_id)
    await configdb.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": True, "start_date": now, "updated_at": now}},
        upsert=True
    )
    return now
