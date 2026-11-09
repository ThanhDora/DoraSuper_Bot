"""Lệnh /autodel và đánh dấu ngữ cảnh lệnh để tự xóa câu trả lời bot."""
from __future__ import annotations

import html
from logging import getLogger

from pyrogram import filters
from pyrogram.types import Message

from database.autodel_db import get_autodel_settings, set_autodel_enabled, set_autodel_seconds
from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.emoji import E_SUCCESS, E_TIP, E_WARN
from dorasuper.helper.autodel import (
    clear_command_context,
    clamp_seconds,
    install_autodel_hooks,
    is_command_text,
    mark_command_context,
    refresh_settings_cache,
    resume_pending_deletes,
)
from dorasuper.vars import COMMAND_HANDLER, SUDO

LOGGER = getLogger("DoraSuper")

__MODULE__ = "TựXóa"
__HELP__ = """
Tự động xóa câu trả lời chữ của bot (và lệnh của bạn nếu bot có quyền) sau một khoảng thời gian.

Áp dụng khi bạn gửi lệnh (/...). File/media tải về, bài /up trên kênh, tin LOG và luồng /up gửi file được giữ lại.

<blockquote>/autodel – Xem trạng thái hiện tại
/autodel &lt;giây&gt; – Bật và đặt thời gian (5–86400), mặc định 60
/autodel on – Bật lại
/autodel off – Tắt</blockquote>
"""

_HANDLER_GROUP_MARK = -100
_HANDLER_GROUP_CLEAR = 1000
_bootstrapped = False


def _is_sudo(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in SUDO)


def _looks_like_command(_, __, message: Message) -> bool:
    if not message or not message.text:
        return False
    prefixes = tuple(COMMAND_HANDLER) if COMMAND_HANDLER else ("/", "!")
    return is_command_text(message.text, prefixes)


@app.on_message(filters.create(_looks_like_command), group=_HANDLER_GROUP_MARK)
async def _autodel_mark_command(_, message: Message):
    global _bootstrapped
    mark_command_context(message)
    if not _bootstrapped:
        _bootstrapped = True
        try:
            await resume_pending_deletes(app)
        except Exception as e:
            LOGGER.warning("autodel resume failed: %s", e)


@app.on_message(filters.create(_looks_like_command), group=_HANDLER_GROUP_CLEAR)
async def _autodel_clear_command(_, message: Message):
    clear_command_context()


@app.on_message(filters.command(["autodel"], COMMAND_HANDLER), group=-2)
@capture_err
async def command_autodel(_, message: Message):
    if not _is_sudo(message):
        await message.reply_text(
            f"{E_WARN} Chỉ admin bot mới chỉnh /autodel.",
            quote=True,
        )
        return
    args = (message.text or "").split(maxsplit=1)
    raw = args[1].strip() if len(args) > 1 else ""
    if not raw:
        settings = await get_autodel_settings()
        state = "bật" if settings["enabled"] else "tắt"
        await message.reply_text(
            f"{E_TIP} Tự xóa trả lời lệnh: <b>{state}</b> — "
            f"<code>{settings['seconds']}</code> giây.\n"
            f"Dùng <code>/autodel 60</code>, <code>/autodel on</code>, <code>/autodel off</code>.",
            quote=True,
        )
        await refresh_settings_cache(force=True)
        return
    low = raw.lower()
    if low in ("off", "tat", "tắt", "disable", "0"):
        settings = await set_autodel_enabled(False)
        await refresh_settings_cache(force=True)
        await message.reply_text(f"{E_SUCCESS} Đã tắt tự xóa trả lời lệnh.", quote=True)
        return
    if low in ("on", "bat", "bật", "enable"):
        settings = await set_autodel_enabled(True)
        await refresh_settings_cache(force=True)
        await message.reply_text(
            f"{E_SUCCESS} Đã bật tự xóa — <code>{settings['seconds']}</code> giây.",
            quote=True,
        )
        return
    if raw.isdigit():
        settings = await set_autodel_seconds(clamp_seconds(int(raw)))
        await refresh_settings_cache(force=True)
        await message.reply_text(
            f"{E_SUCCESS} Đã đặt tự xóa sau <code>{settings['seconds']}</code> giây.",
            quote=True,
        )
        return
    await message.reply_text(
        f"{E_WARN} Không hiểu. Thử <code>/autodel 60</code>, <code>on</code> hoặc <code>off</code>.",
        quote=True,
    )


# Install hooks as soon as plugin imports (app already started).
try:
    install_autodel_hooks(app)
except Exception as e:
    LOGGER.error("install_autodel_hooks failed: %s", e)
