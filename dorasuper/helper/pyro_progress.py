#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Shrimadhav U K — redesigned by DoraSuper

import math
import time

try:
    from pyrogram.enums import ParseMode
    from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified
except Exception:  # pragma: no cover - allow pure helpers without pyrogram
    ParseMode = None

    class FloodWait(Exception):
        value = 10

    class MessageIdInvalid(Exception):
        pass

    class MessageNotModified(Exception):
        pass

from dorasuper.emoji import (
    E_CLOCK, E_FIRE, E_GLOBE, E_NOTE, E_ROCKET, E_SPARKLE, E_STAT, E_WAIT,
)

UPDATE_INTERVAL = 3.0
BAR_LEN = 20
# key -> next allowed edit timestamp
_NEXT_EDIT: dict = {}


def should_update_progress(key, current, total, now=None, interval=UPDATE_INTERVAL, store=None):
    """Throttle: at most one edit per `interval` seconds; always allow completion."""
    store = _NEXT_EDIT if store is None else store
    now = time.time() if now is None else now
    if total and current >= total:
        store.pop(key, None)
        return True
    if now < store.get(key, 0):
        return False
    store[key] = now + interval
    return True


def progress_bar(percentage: float, length: int = BAR_LEN) -> str:
    filled = max(0, min(length, math.floor(percentage * length / 100)))
    return "█" * filled + "░" * (length - filled)


def format_progress_html(current, total, elapsed, dc_id, ud_type) -> str:
    total = total or 0
    percentage = (current * 100 / total) if total > 0 else 0.0
    percentage = min(percentage, 100.0)
    speed = current / elapsed if elapsed and elapsed > 0 else 0
    if total and current >= total:
        eta = "0 giây"
    elif speed > 0 and total > current:
        eta = time_formatter(round((total - current) / speed)) or "0 giây"
    else:
        eta = "đang tính..."
    return (
        f"{ud_type}\n\n"
        f"{E_SPARKLE} <code>[{progress_bar(percentage)}]</code>\n"
        f"{E_STAT} <b>Tiến trình:</b> {round(percentage, 2)}%\n"
        f"{E_NOTE} <b>Đã tải:</b> {humanbytes(current) or '0 B'} / {humanbytes(total) or '?'}\n"
        f"{E_ROCKET} <b>Tốc độ:</b> {humanbytes(speed) or '0 B'}/s {E_FIRE}\n"
        f"{E_GLOBE} <b>Máy chủ DC:</b> {dc_id if dc_id not in (None, '') else '-'}\n"
        f"{E_WAIT} <b>Còn lại:</b> {eta}\n"
        f"{E_CLOCK} <b>Đã chạy:</b> {time_formatter(round(elapsed or 0)) or '0 giây'}"
    )


async def progress_for_pyrogram(current, total, ud_type, message, start, dc_id):
    """Progress callback. Never blocks the transfer (no sleeping on FloodWait)."""
    now = time.time()
    chat = getattr(message, "chat", None)
    key = (getattr(chat, "id", None), getattr(message, "id", id(message)))
    if not should_update_progress(key, current, total, now):
        return
    text = format_progress_html(current, total, now - start, dc_id, ud_type)
    try:
        if ParseMode is not None:
            await message.edit(text, parse_mode=ParseMode.HTML)
        else:
            await message.edit(text)
    except FloodWait as e:
        # back off without blocking the download/upload
        _NEXT_EDIT[key] = now + float(getattr(e, "value", 10) or 10) + 1
    except Exception:
        # MessageNotModified / MessageIdInvalid / others: never break the transfer
        pass


def humanbytes(size) -> str:
    """converts bytes into human readable format"""
    if not size:
        return ""
    power = 2**10
    number = 0
    dict_power_n = {0: "", 1: "Ki", 2: "Mi", 3: "Gi", 4: "Ti"}
    while size > power and number < 4:
        size /= power
        number += 1
    return f"{round(size, 2)} {dict_power_n[number]}B"


def time_formatter(seconds) -> str:
    seconds = int(seconds or 0)
    parts = []
    for name, div in (("ngày", 86400), ("giờ", 3600), ("phút", 60), ("giây", 1)):
        v, seconds = divmod(seconds, div)
        if v:
            parts.append(f"{v} {name}")
    return " ".join(parts)
