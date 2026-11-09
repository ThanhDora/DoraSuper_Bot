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
    "files": None,
    "pm": None,
    "new_groups": None,
    "errors": None,
}

# Định nghĩa các topic cần tạo: (key trong DB, tên topic)
_TOPICS_DEF = [
    ("commands",   "📋 Lệnh"),
    ("photos",     "📷 Ảnh"),
    ("videos",     "🎬 Video"),
    ("files",      "File"),
    ("pm",         "Tin nhắn riêng"),
    ("new_groups", "🆕 Nhóm Mới"),
    ("errors",     "⚠️ Lỗi & Admin"),
]


# Từ khoá khớp lỏng (substring, không phân biệt hoa thường) khi tiêu đề topic khác chút
_TOPIC_KEYWORDS = {
    "commands":   ("lệnh", "command"),
    "photos":     ("ảnh", "photo"),
    "videos":     ("video",),
    "files":      ("file", "tài liệu", "document"),
    "pm":         ("tin nhắn riêng", "nhắn riêng", "private", "pm"),
    "new_groups": ("nhóm mới", "new group"),
    "errors":     ("lỗi", "error"),
}


async def _get_raw_messages(app, channel, ids):
    from pyrogram import raw
    r = await app.invoke(
        raw.functions.channels.GetMessages(channel=channel, id=[raw.types.InputMessageID(id=i) for i in ids]),
        sleep_threshold=0,  # không ngủ chờ FloodWait trong lúc khởi động
    )
    return [m for m in r.messages if not isinstance(m, raw.types.MessageEmpty)]


async def _scan_range(app, start: int, deadline: float | None, found: dict, batch: int = 200) -> tuple[int, bool]:
    """Quét tin theo ID (raw GetMessages, 200 ID/lần). Tin dịch vụ 'tạo topic' có id == thread_id.
    Trả về (id kế tiếp cần quét, đã hết tin chưa). deadline=None → chạy nền, tôn trọng FloodWait."""
    import asyncio
    import time
    from pyrogram import raw
    from pyrogram.errors import FloodWait
    peer = await app.resolve_peer(LOG_CHANNEL)
    channel = raw.types.InputChannel(channel_id=peer.channel_id, access_hash=peer.access_hash)
    max_seen, cur = start - 1, start
    while True:
        if deadline is not None and time.monotonic() > deadline:
            return cur, False
        try:
            msgs = await _get_raw_messages(app, channel, range(cur, cur + batch))
        except FloodWait as e:
            if deadline is not None:
                return cur, False
            await asyncio.sleep(int(getattr(e, "value", 10) or 10) + 1)
            continue
        for m in msgs:
            max_seen = max(max_seen, m.id)
            act = getattr(m, "action", None)
            if isinstance(m, raw.types.MessageService) and isinstance(act, raw.types.MessageActionTopicCreate):
                found[int(m.id)] = act.title
            elif isinstance(m, raw.types.MessageService) and isinstance(act, raw.types.MessageActionTopicEdit) and act.title:
                rt = getattr(m, "reply_to", None)
                tid = getattr(rt, "reply_to_top_id", None) or getattr(rt, "reply_to_msg_id", None)
                if tid:
                    found[int(tid)] = act.title
        cur += batch
        if cur > max_seen + 2000:  # 10 lô rỗng liên tiếp → hết tin
            return cur, True
        if _all_matched(found):
            return cur, False


def _all_matched(found: dict) -> bool:
    used: set = set()
    for key, name in _TOPICS_DEF:
        m = _match_topic(key, name, found, used)
        if not m:
            return False
        used.add(m)
    return True


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


def _apply(saved: dict, found: dict) -> dict:
    mapping, used = {}, set()
    for key, _ in _TOPICS_DEF:
        if saved.get(key):
            used.add(saved[key])
    for key, name in _TOPICS_DEF:
        tid = saved.get(key)
        if tid:
            mapping[key] = tid
            continue
        m = _match_topic(key, name, found, used)
        if m:
            used.add(m)
            LOGGER.info("LOG_TOPIC [%s] khớp topic có sẵn '%s': thread_id=%s", key, found[m], m)
        mapping[key] = m
    return mapping


def _publish(mapping: dict) -> None:
    for k, v in mapping.items():
        LOG_TOPIC_IDS[k] = v
    LOGGER.info(
        "LOG_TOPICS: commands=%s, photos=%s, videos=%s, files=%s, pm=%s, new_groups=%s, errors=%s",
        LOG_TOPIC_IDS["commands"], LOG_TOPIC_IDS["photos"], LOG_TOPIC_IDS["videos"],
        LOG_TOPIC_IDS["files"], LOG_TOPIC_IDS["pm"],
        LOG_TOPIC_IDS["new_groups"], LOG_TOPIC_IDS["errors"],
    )


async def _background_scan(app, saved: dict, found: dict, start: int) -> None:
    try:
        nxt, _ = await _scan_range(app, start, None, found)
        mapping = _apply(saved, found)
        await _col.update_one({"_id": "log_topics"}, {"$set": {**{k: v for k, v in mapping.items() if v}, "scan_next": nxt}}, upsert=True)
        _publish(mapping)
        missing = [k for k, v in mapping.items() if v is None]
        if missing:
            LOGGER.warning("LOG_TOPICS: quét xong vẫn thiếu %s — đặt LOG_TOPIC_IDS trong config.env hoặc cấp quyền Manage Topics", missing)
    except Exception as e:
        LOGGER.warning("LOG_TOPICS: quét nền lỗi: %s", e)


async def ensure_log_topics(app) -> None:
    """Xác định thread_id các tab log: config.env > Mongo > quét tin 'tạo topic' (≤10s, phần còn lại chạy nền) > tạo mới."""
    import asyncio
    import os
    import time
    saved = {k: v for k, v in (await _col.find_one({"_id": "log_topics"}) or {}).items() if k in LOG_TOPIC_IDS and v}
    for part in (os.environ.get("LOG_TOPIC_IDS") or "").split(","):
        k, _, v = part.partition(":")
        if k.strip() in LOG_TOPIC_IDS and v.strip().isdigit():
            saved[k.strip()] = int(v.strip())
    if all(saved.get(k) for k, _ in _TOPICS_DEF):
        LOGGER.info("LOG_TOPICS: dùng ID đã lưu/config, không cần quét")
        await _col.update_one({"_id": "log_topics"}, {"$set": {k: saved[k] for k, _ in _TOPICS_DEF}}, upsert=True)
        _publish(saved)
        return

    found: dict[int, str] = {}
    nxt, done = 1, False
    try:
        nxt, done = await _scan_range(app, 1, time.monotonic() + 10, found)
    except Exception as e:
        LOGGER.warning("LOG_TOPICS: quét nhanh lỗi: %s", e)
    mapping = _apply(saved, found)

    for key, name in _TOPICS_DEF:
        if mapping[key] is None and done:  # chỉ tạo khi đã quét hết mà vẫn không có
            try:
                t = await app.create_forum_topic(chat_id=LOG_CHANNEL, title=name)
                mapping[key] = t.id
                LOGGER.info("LOG_TOPIC [%s] đã tạo mới: thread_id=%s", key, t.id)
            except Exception as e:
                LOGGER.error("LOG_TOPIC [%s] không tạo được topic: %s", key, e)

    await _col.update_one({"_id": "log_topics"}, {"$set": {k: v for k, v in mapping.items() if v}}, upsert=True)
    _publish(mapping)
    if any(v is None for v in mapping.values()) and not done:
        LOGGER.info("LOG_TOPICS: chưa đủ, tiếp tục quét nền từ id %s", nxt)
        saved_now = {k: v for k, v in mapping.items() if v}
        asyncio.create_task(_background_scan(app, saved_now, found, nxt))


def topic_id(key: str) -> int | None:
    """Lấy thread_id cho key; cảnh báo nếu chưa có (log sẽ rơi vào General)."""
    tid = LOG_TOPIC_IDS.get(key)
    if tid is None:
        LOGGER.warning("LOG_TOPIC [%s] chưa có thread_id, gửi vào General", key)
    return tid
