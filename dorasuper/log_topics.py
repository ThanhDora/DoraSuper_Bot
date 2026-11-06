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


# Từ khoá khớp lỏng (substring, không phân biệt hoa thường) khi tiêu đề topic khác chút
_TOPIC_KEYWORDS = {
    "commands":   ("lệnh", "command"),
    "photos":     ("ảnh", "photo"),
    "videos":     ("video",),
    "new_groups": ("nhóm mới", "new group"),
    "errors":     ("lỗi", "error"),
}


async def _list_forum_topics(app) -> dict[int, str] | None:
    """Trả về {thread_id: title} các topic hiện có trong LOG_CHANNEL, None nếu không liệt kê được."""
    topics: dict[int, str] = {}
    try:
        if hasattr(app, "get_forum_topics"):
            async for t in app.get_forum_topics(LOG_CHANNEL):
                tid = getattr(t, "id", None) or getattr(t, "message_thread_id", None)
                if tid:
                    topics[int(tid)] = getattr(t, "title", "") or ""
            return topics
        from pyrogram import raw
        peer = await app.resolve_peer(LOG_CHANNEL)
        offset_id = offset_topic = offset_date = 0
        while True:
            fn = getattr(raw.functions.channels, "GetForumTopics", None) or raw.functions.messages.GetForumTopics
            kw = dict(offset_date=offset_date, offset_id=offset_id, offset_topic=offset_topic, limit=100)
            kw["channel" if fn.__module__.endswith("channels") else "peer"] = peer
            r = await app.invoke(fn(**kw))
            batch = [t for t in r.topics if hasattr(t, "title")]
            for t in batch:
                topics[int(t.id)] = t.title
            if len(batch) < 100:
                break
            last = batch[-1]
            offset_topic, offset_id, offset_date = last.id, last.top_message, last.date
        return topics
    except Exception as e:
        LOGGER.warning("LOG_TOPICS: không liệt kê được forum topics (%s) — bot cần quyền admin + Manage Topics", e)
        return None


def _match_topic(key: str, name: str, topics: dict[int, str], used: set) -> int | None:
    norm = lambda x: " ".join(x.casefold().split())
    for tid, title in topics.items():
        if tid not in used and norm(title) == norm(name):
            return tid
    for tid, title in topics.items():
        if tid in used:
            continue
        t = norm(title)
        if any(k in t for k in _TOPIC_KEYWORDS.get(key, ())):
            return tid
    return None


async def ensure_log_topics(app) -> None:
    """Xác định topic IDs cho LOG_CHANNEL: dùng lại ID đã lưu/topic sẵn có theo tên, chỉ tạo khi thiếu."""
    saved = await _col.find_one({"_id": "log_topics"}) or {}
    topics = await _list_forum_topics(app)

    mapping: dict[str, int | None] = {}
    used: set = set()
    for key, name in _TOPICS_DEF:
        topic_id = saved.get(key)
        if topic_id and (topics is None or topic_id in topics):
            mapping[key] = topic_id
            used.add(topic_id)
            LOGGER.info("LOG_TOPIC [%s] dùng lại ID đã lưu: thread_id=%s", key, topic_id)
            continue
        if topic_id:
            LOGGER.warning("LOG_TOPIC [%s] ID đã lưu %s không còn tồn tại", key, topic_id)
        matched = _match_topic(key, name, topics or {}, used)
        if matched:
            mapping[key] = matched
            used.add(matched)
            LOGGER.info("LOG_TOPIC [%s] khớp topic có sẵn '%s': thread_id=%s", key, topics[matched], matched)
            continue
        try:
            forum_topic = await app.create_forum_topic(chat_id=LOG_CHANNEL, title=name)
            mapping[key] = forum_topic.id
            used.add(forum_topic.id)
            LOGGER.info("LOG_TOPIC [%s] đã tạo mới: thread_id=%s", key, forum_topic.id)
        except Exception as e:
            LOGGER.error("LOG_TOPIC [%s] không tìm thấy và không tạo được topic: %s", key, e)
            mapping[key] = None

    await _col.update_one({"_id": "log_topics"}, {"$set": mapping}, upsert=True)
    for k, v in mapping.items():
        LOG_TOPIC_IDS[k] = v

    LOGGER.info(
        "LOG_TOPICS: commands=%s, photos=%s, videos=%s, new_groups=%s, errors=%s",
        LOG_TOPIC_IDS["commands"], LOG_TOPIC_IDS["photos"], LOG_TOPIC_IDS["videos"],
        LOG_TOPIC_IDS["new_groups"], LOG_TOPIC_IDS["errors"],
    )
    missing = [k for k, v in LOG_TOPIC_IDS.items() if v is None]
    if missing:
        LOGGER.warning("LOG_TOPICS thiếu %s — log loại này sẽ vào General", missing)


def topic_id(key: str) -> int | None:
    """Lấy thread_id cho key; cảnh báo nếu chưa có (log sẽ rơi vào General)."""
    tid = LOG_TOPIC_IDS.get(key)
    if tid is None:
        LOGGER.warning("LOG_TOPIC [%s] chưa có thread_id, gửi vào General", key)
    return tid
