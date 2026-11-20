"""In-process MTProto heartbeat for hang detection (no second client)."""
from __future__ import annotations

import asyncio
import os
import time
from logging import getLogger
from typing import Optional

LOGGER = getLogger("DoraSuper")

DEFAULT_PATH = "/run/bot-watchdog/dorasuper.heartbeat"
DEFAULT_INTERVAL = 60
DEFAULT_TIMEOUT = 30


def heartbeat_path() -> str:
    return os.environ.get("BOT_HEARTBEAT_PATH", DEFAULT_PATH)


def touch_heartbeat(path: str, now: Optional[float] = None) -> None:
    """Atomically write a unix timestamp to the heartbeat file."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    stamp = f"{(now if now is not None else time.time()):.3f}\n"
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, stamp.encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def read_heartbeat(path: str) -> Optional[float]:
    try:
        with open(path, "r", encoding="ascii") as fh:
            return float(fh.read().strip())
    except (OSError, ValueError):
        return None


async def ping_mtproto(client) -> None:
    """Hit the live MTProto socket. ``get_me()`` is often cached and would not detect a dead session."""
    from pyrogram import raw

    ping_cls = getattr(raw.functions, "Ping", None)
    if ping_cls is not None:
        await client.invoke(ping_cls(ping_id=0))
        return
    get_state = getattr(getattr(raw.functions, "updates", None), "GetState", None)
    if get_state is not None:
        await client.invoke(get_state())
        return
    # Last resort: force a network user fetch (InputUserSelf), not the cached client.me
    await client.invoke(
        raw.functions.users.GetUsers(id=[raw.types.InputUserSelf()])
    )


async def heartbeat_loop(
    client,
    path: Optional[str] = None,
    interval: int = DEFAULT_INTERVAL,
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    path = path or heartbeat_path()
    LOGGER.info("heartbeat loop started path=%s interval=%ss timeout=%ss", path, interval, timeout)
    while True:
        try:
            await asyncio.wait_for(ping_mtproto(client), timeout=timeout)
            touch_heartbeat(path)
        except Exception as exc:
            LOGGER.warning("heartbeat ping failed: %s", exc)
        await asyncio.sleep(interval)
