# Quản lý Forum Topics cho LOG_CHANNEL
# Tạo các topic khi bot khởi động, lưu topic IDs vào MongoDB.

from logging import getLogger

from async_pymongo import AsyncClient

from dorasuper.vars import DATABASE_NAME, DATABASE_URI, LOG_CHANNEL

LOGGER = getLogger("DoraSuper")

_mongo = AsyncClient(DATABASE_URI)
_db = _mongo[DATABASE_NAME]
_col = _db["log_topics"]

# Dict chứa topic IDs — dùng dict (mutable) để các module import luôn thấy giá trị mới nhất
# Các plugin import dict này rồi truy cập bằng key: LOG_TOPIC_IDS["commands"]
LOG_TOPIC_IDS: dict[str, int | None] = {
    "commands": None,
    "photos": None,
    "videos": None,
    "new_groups": None,
    "errors": None,
}

# Định nghĩa các topic cần tạo: (key trong DB, tên topic)
_TOPICS_DEF = [
    ("commands",   "📋 Lệnh"),
    ("photos",     "📷 Ảnh"),
    ("videos",     "🎬 Video"),
    ("new_groups", "🆕 Nhóm Mới"),
    ("errors",     "⚠️ Lỗi & Admin"),
]


async def ensure_log_topics(app) -> None:
    """Tạo forum topics trong LOG_CHANNEL nếu chưa có. Gọi 1 lần lúc bot start."""

    # Lấy topic IDs đã lưu trong DB
    saved = await _col.find_one({"_id": "log_topics"})
    if not saved:
        saved = {}

    mapping = {}
    for key, name in _TOPICS_DEF:
        topic_id = saved.get(key)
        if topic_id:
            mapping[key] = topic_id
            LOGGER.info("LOG_TOPIC [%s] đã có: thread_id=%s", key, topic_id)
        else:
            # Tạo topic mới
            try:
                forum_topic = await app.create_forum_topic(
                    chat_id=LOG_CHANNEL,
                    title=name,
                )
                mapping[key] = forum_topic.id
                LOGGER.info("LOG_TOPIC [%s] đã tạo: thread_id=%s", key, forum_topic.id)
            except Exception as e:
                LOGGER.error("Không tạo được topic [%s]: %s", key, e)
                mapping[key] = None

    # Lưu vào DB
    await _col.update_one(
        {"_id": "log_topics"},
        {"$set": mapping},
        upsert=True,
    )

    # Gán vào dict global (các module import dict này sẽ thấy giá trị mới)
    for k, v in mapping.items():
        LOG_TOPIC_IDS[k] = v

    LOGGER.info(
        "LOG_TOPICS: commands=%s, photos=%s, videos=%s, new_groups=%s, errors=%s",
        LOG_TOPIC_IDS["commands"], LOG_TOPIC_IDS["photos"], LOG_TOPIC_IDS["videos"],
        LOG_TOPIC_IDS["new_groups"], LOG_TOPIC_IDS["errors"],
    )
