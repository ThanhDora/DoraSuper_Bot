from dorasuper.helper.yeta_media import vn_date_str
from database import dbname

videoquotadb = dbname["media_gen_video_quota"]


async def get_video_used(user_id: int) -> int:
    doc = await videoquotadb.find_one({"user_id": user_id, "date": vn_date_str()})
    return int(doc.get("count", 0)) if doc else 0


async def add_video_used(user_id: int) -> int:
    day = vn_date_str()
    await videoquotadb.update_one(
        {"user_id": user_id, "date": day}, {"$inc": {"count": 1}}, upsert=True
    )
    return await get_video_used(user_id)
