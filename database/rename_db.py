# Cài đặt đổi tên file theo từng người dùng (prefix, suffix, caption, thumbnail, metadata)

from database import dbname

rename_coll = dbname["file_rename"]

DEFAULT_METADATA = (
    "--change-title DoraSuper\n"
    "--change-video-title DoraSuper\n"
    "--change-audio-title DoraSuper\n"
    "--change-subtitle-title DoraSuper\n"
    "--change-author DoraSuper"
)


async def get_settings(user_id: int) -> dict:
    return await rename_coll.find_one({"_id": int(user_id)}) or {}


async def set_field(user_id: int, key: str, value):
    await rename_coll.update_one({"_id": int(user_id)}, {"$set": {key: value}}, upsert=True)


async def del_field(user_id: int, key: str):
    await rename_coll.update_one({"_id": int(user_id)}, {"$unset": {key: ""}})


async def get_field(user_id: int, key: str, default=None):
    return (await get_settings(user_id)).get(key, default)
