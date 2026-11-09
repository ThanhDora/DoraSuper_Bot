"""Global auto-delete for bot replies to user commands."""
from __future__ import annotations

import asyncio
import contextvars
import time
from contextlib import asynccontextmanager, contextmanager
from logging import getLogger
from typing import Optional

LOGGER = getLogger("DoraSuper")

_command_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar("autodel_cmd", default=False)
_exclude_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar("autodel_exclude", default=False)
_user_cmd_msg_ctx: contextvars.ContextVar[object] = contextvars.ContextVar("autodel_user_msg", default=None)

_installed = False
_DEFAULT_SECONDS = 60
_MIN_SECONDS = 5
_MAX_SECONDS = 86400

# In-memory cache of settings
_cache = {"enabled": True, "seconds": _DEFAULT_SECONDS, "loaded_at": 0.0}


def clamp_seconds(seconds: int) -> int:
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        value = _DEFAULT_SECONDS
    return max(_MIN_SECONDS, min(_MAX_SECONDS, value))


def is_command_text(text: str, prefixes=("/", "!")) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    return text.startswith(tuple(prefixes))


def message_is_media(msg) -> bool:
    if msg is None:
        return False
    for attr in (
        "photo", "video", "document", "audio", "animation",
        "voice", "video_note", "sticker", "media_group_id",
    ):
        if getattr(msg, attr, None):
            return True
    return False


def should_autodel_bot_message(msg, *, exclude: bool = False, in_command: bool = False) -> bool:
    """Pure decision: delete text/notice bot replies during command handling."""
    if exclude or not in_command or msg is None:
        return False
    if message_is_media(msg):
        return False
    # Keep empty / service-ish
    if not (getattr(msg, "text", None) or getattr(msg, "caption", None)):
        # sticker-only etc already media; pure empty skip
        return False
    # If it has a document/photo even with caption, message_is_media caught it
    return True


def mark_command_context(message=None):
    _command_ctx.set(True)
    if message is not None:
        _user_cmd_msg_ctx.set(message)


def clear_command_context():
    _command_ctx.set(False)
    _user_cmd_msg_ctx.set(None)


def in_command_context() -> bool:
    return bool(_command_ctx.get())


@contextmanager
def skip_autodel():
    token = _exclude_ctx.set(True)
    try:
        yield
    finally:
        _exclude_ctx.reset(token)


@asynccontextmanager
async def askip_autodel():
    token = _exclude_ctx.set(True)
    try:
        yield
    finally:
        _exclude_ctx.reset(token)


async def refresh_settings_cache(force: bool = False) -> dict:
    now = time.time()
    if not force and _cache["loaded_at"] and now - _cache["loaded_at"] < 5:
        return {"enabled": _cache["enabled"], "seconds": _cache["seconds"]}
    try:
        from database.autodel_db import get_autodel_settings
        settings = await get_autodel_settings()
        _cache["enabled"] = bool(settings.get("enabled", True))
        _cache["seconds"] = clamp_seconds(settings.get("seconds", _DEFAULT_SECONDS))
        _cache["loaded_at"] = now
    except Exception as e:
        LOGGER.warning("autodel settings load failed: %s", e)
    return {"enabled": _cache["enabled"], "seconds": _cache["seconds"]}


async def _delete_later(app, chat_id: int, message_id: int, delay: float, user_message_id=None):
    try:
        await asyncio.sleep(max(0.0, delay))
        ids = [message_id]
        if user_message_id:
            ids.append(int(user_message_id))
        try:
            await app.delete_messages(chat_id, ids)
        except Exception:
            # try one by one
            for mid in ids:
                try:
                    await app.delete_messages(chat_id, mid)
                except Exception:
                    pass
    finally:
        try:
            from database.autodel_db import remove_pending_delete
            await remove_pending_delete(chat_id, message_id)
        except Exception:
            pass


async def schedule_autodel(app, msg, *, user_command_message=None, seconds: Optional[int] = None):
    if msg is None:
        return
    settings = await refresh_settings_cache()
    if not settings["enabled"]:
        return
    delay = clamp_seconds(seconds if seconds is not None else settings["seconds"])
    chat_id = msg.chat.id if msg.chat else None
    if chat_id is None:
        return
    # Never autodel in LOG channel
    try:
        from dorasuper.vars import LOG_CHANNEL
        if LOG_CHANNEL and int(chat_id) == int(LOG_CHANNEL):
            return
    except Exception:
        pass
    user_mid = None
    if user_command_message is not None:
        user_mid = getattr(user_command_message, "id", None)
    delete_at = time.time() + delay
    try:
        from database.autodel_db import add_pending_delete
        await add_pending_delete(chat_id, msg.id, delete_at, user_mid)
    except Exception as e:
        LOGGER.debug("autodel persist failed: %s", e)
    asyncio.create_task(_delete_later(app, chat_id, msg.id, delay, user_mid))


async def _maybe_autodel_result(app, result, *, no_autodel: bool = False):
    if no_autodel or _exclude_ctx.get() or not _command_ctx.get():
        return result
    if not should_autodel_bot_message(
        result, exclude=False, in_command=True,
    ):
        return result
    user_msg = _user_cmd_msg_ctx.get()
    await schedule_autodel(app, result, user_command_message=user_msg)
    return result


def install_autodel_hooks(app) -> None:
    """Monkeypatch reply_text / send_message once."""
    global _installed
    if _installed:
        return
    from pyrogram.types import Message

    orig_reply_text = Message.reply_text

    async def reply_text_patched(self, text, *args, **kwargs):
        no_autodel = bool(kwargs.pop("no_autodel", False))
        result = await orig_reply_text(self, text, *args, **kwargs)
        try:
            await _maybe_autodel_result(app, result, no_autodel=no_autodel)
        except Exception as e:
            LOGGER.debug("autodel after reply_text: %s", e)
        return result

    Message.reply_text = reply_text_patched

    # reply() often used for text
    if hasattr(Message, "reply"):
        orig_reply = Message.reply

        async def reply_patched(self, *args, **kwargs):
            no_autodel = bool(kwargs.pop("no_autodel", False))
            result = await orig_reply(self, *args, **kwargs)
            try:
                # only autodel pure text replies
                if result and not message_is_media(result):
                    await _maybe_autodel_result(app, result, no_autodel=no_autodel)
            except Exception as e:
                LOGGER.debug("autodel after reply: %s", e)
            return result

        Message.reply = reply_patched

    orig_send_message = app.send_message.__func__ if hasattr(app.send_message, "__func__") else None
    # Client.send_message is a bound method; patch on class
    from pyrogram import Client
    orig_client_send = Client.send_message

    async def send_message_patched(self, chat_id, text, *args, **kwargs):
        no_autodel = bool(kwargs.pop("no_autodel", False))
        # Exclude LOG_CHANNEL by destination
        try:
            from dorasuper.vars import LOG_CHANNEL
            if LOG_CHANNEL and int(chat_id) == int(LOG_CHANNEL):
                no_autodel = True
        except Exception:
            pass
        result = await orig_client_send(self, chat_id, text, *args, **kwargs)
        try:
            await _maybe_autodel_result(self, result, no_autodel=no_autodel)
        except Exception as e:
            LOGGER.debug("autodel after send_message: %s", e)
        return result

    Client.send_message = send_message_patched
    _installed = True
    LOGGER.info("autodel hooks installed")


async def resume_pending_deletes(app) -> None:
    try:
        from database.autodel_db import list_pending_deletes
        rows = await list_pending_deletes(1000)
    except Exception as e:
        LOGGER.warning("autodel resume list failed: %s", e)
        return
    now = time.time()
    for row in rows:
        chat_id = row.get("chat_id")
        message_id = row.get("message_id")
        delete_at = float(row.get("delete_at") or now)
        delay = max(0.0, delete_at - now)
        user_mid = row.get("user_message_id")
        asyncio.create_task(_delete_later(app, chat_id, message_id, delay, user_mid))
    if rows:
        LOGGER.info("autodel resumed %s pending deletes", len(rows))
