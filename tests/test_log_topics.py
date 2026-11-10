"""Offline tests for LOG topic name matching (downloads vs files)."""
import logging
from pathlib import Path


def _load():
    text = Path(__file__).resolve().parents[1].joinpath("dorasuper/log_topics.py").read_text(encoding="utf-8")
    start = text.index("LOG_TOPIC_IDS:")
    end = text.index("async def _background_scan_high")
    ns = {"LOGGER": logging.getLogger("test_log_topics")}
    exec(text[start:end], ns)
    return ns


def test_downloads_key_and_canonical_name():
    ns = _load()
    assert "downloads" in ns["LOG_TOPIC_IDS"]
    names = dict(ns["_TOPICS_DEF"])
    assert names["downloads"] == "Lượt tải file"
    kws = ns["_TOPIC_KEYWORDS"]["downloads"]
    assert "lượt tải file" in kws
    assert "tải file" in kws
    assert "downloads" in kws


def test_exact_and_alias_match():
    ns = _load()
    match = ns["_match_topic"]
    used = set()
    topics = {
        10: "📋 Lệnh",
        20: "File",
        30: "Lượt tải file",
    }
    assert match("files", "File", topics, used) == 20
    used.add(20)
    assert match("downloads", "Lượt tải file", topics, used) == 30


def test_alias_titles_do_not_steal_file_topic():
    ns = _load()
    apply = ns["_apply"]
    found = {
        8498: "File",
        9001: "Tải file",
        3160: "Lệnh",
        3161: "Ảnh",
        3162: "Video",
        3163: "Nhóm Mới",
        3164: "Lỗi & Admin",
        4000: "Tin nhắn riêng",
    }
    mapping = apply({}, found)
    assert mapping["files"] == 8498
    assert mapping["downloads"] == 9001

    found2 = {
        8498: "File",
        9002: "Downloads",
    }
    mapping2 = apply({"files": 8498}, found2)
    assert mapping2["files"] == 8498
    assert mapping2["downloads"] == 9002

    found3 = {8498: "File", 9003: "Lượt tải"}
    mapping3 = apply({"files": 8498}, found3)
    assert mapping3["downloads"] == 9003


def test_only_tai_file_does_not_bind_as_files():
    ns = _load()
    mapping = ns["_apply"]({}, {9001: "Tải file"})
    assert mapping["files"] is None
    assert mapping["downloads"] == 9001
