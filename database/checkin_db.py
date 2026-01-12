from typing import List, Dict, Optional, Union
from datetime import datetime
from zoneinfo import ZoneInfo
from database import dbname

checkindb = dbname["checkin"]
configdb = dbname["checkin_config"]
usagedb = dbname["checkin_usage"]

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

def _vn_date(dt_utc: datetime):
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
    return dt_utc.astimezone(VN_TZ).date()

async def get_user_command_usage(chat_id: int, user_id: int, command: str) -> Union[dict, bool]:
    usage = await usagedb.find_one({"chat_id": chat_id, "user_id": user_id, "command": command})
    return usage if usage else False

async def update_user_command_usage(chat_id: int, user_id: int, command: str):
    await usagedb.update_one(
        {"chat_id": chat_id, "user_id": user_id, "command": command},
        {"$set": {"chat_id": chat_id, "user_id": user_id, "command": command, "last_used": datetime.utcnow()}},
        upsert=True
    )

async def can_use_command(chat_id: int, user_id: int, command: str) -> bool:
    usage = await get_user_command_usage(chat_id, user_id, command)
    if not usage: return True
    last_used = usage.get("last_used")
    if not last_used: return True
    last_day_vn = _vn_date(last_used.replace(tzinfo=ZoneInfo("UTC")) if last_used.tzinfo is None else last_used)
    now_day_vn = _vn_date(datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")))
    return now_day_vn != last_day_vn

async def ensure_chat_config(chat_id: int) -> dict:
    cfg = await configdb.find_one({"chat_id": chat_id})
    if cfg: return cfg
    now = datetime.utcnow()
    cfg = {"chat_id": chat_id, "enabled": True, "start_date": now}
    await configdb.insert_one(cfg)
    return cfg

async def is_checkin_enabled(chat_id: int) -> bool:
    cfg = await ensure_chat_config(chat_id)
    return bool(cfg.get("enabled", True))

async def set_checkin_enabled(chat_id: int, enabled: bool):
    await configdb.update_one({"chat_id": chat_id}, {"$set": {"enabled": enabled}}, upsert=True)

async def get_checkin_start_date(chat_id: int) -> datetime:
    cfg = await ensure_chat_config(chat_id)
    return cfg.get("start_date") or datetime.utcnow()

async def log_checkin(chat_id: int, user_id: int, user_name: str) -> datetime:
    ts_utc = datetime.utcnow()
    vn = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(VN_TZ)
    doc = {"chat_id": chat_id, "user_id": user_id, "user_name": user_name, "ts": ts_utc, "y": vn.year, "m": vn.month, "d": vn.day}
    await checkindb.insert_one(doc)
    return ts_utc

async def get_user_total(chat_id: int, user_id: int, year: Optional[int] = None, month: Optional[int] = None) -> int:
    q = {"chat_id": chat_id, "user_id": user_id}
    if year: q["y"] = year
    if month: q["m"] = month
    return await checkindb.count_documents(q)

async def get_last_checkin(chat_id: int, user_id: int) -> Optional[datetime]:
    last = await checkindb.find_one({"chat_id": chat_id, "user_id": user_id}, sort=[("ts", -1)])
    return last["ts"] if last else None

async def get_top10(chat_id: int, year: Optional[int] = None, month: Optional[int] = None) -> List[dict]:
    q = {"chat_id": chat_id}
    if year: q["y"] = year
    if month: q["m"] = month
    pipeline = [{"$match": q}, {"$group": {"_id": "$user_id", "count": {"$sum": 1}, "user_name": {"$last": "$user_name"}, "ts": {"$max": "$ts"}}}, {"$sort": {"count": -1, "ts": 1}}, {"$limit": 10}]
    return await checkindb.aggregate(pipeline).to_list(10)

async def reset_checkin(chat_id: int) -> datetime:
    now = datetime.utcnow()
    await checkindb.delete_many({"chat_id": chat_id})
    await usagedb.delete_many({"chat_id": chat_id})
    await configdb.update_one({"chat_id": chat_id}, {"$set": {"start_date": now}}, upsert=True)
    return now