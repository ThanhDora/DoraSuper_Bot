"""Pure helpers for the group/global whitelist (no Telegram client, no Mongo)."""
from __future__ import annotations

import unicodedata
from typing import Iterable, Optional

GLOBAL_CHAT_ID = 0

PROTECTED_HTML = (
    "{mention} đang trong danh sách trắng, không thể bị mute, cấm hoặc đá "
    "dưới mọi hình thức."
)
AUTO_UNBAN_HTML = (
    "Đã tự động bỏ cấm {mention} vì người này nằm trong danh sách trắng."
)
AUTO_UNRESTRICT_HTML = (
    "Đã tự động gỡ hạn chế {mention} vì người này nằm trong danh sách trắng."
)
MISSING_RIGHTS_HTML = (
    "Không thể tự động bỏ cấm/gỡ hạn chế {mention}: bot cần quyền hạn chế thành viên."
)


def protected_html(mention: str) -> str:
    return PROTECTED_HTML.format(mention=mention or "Người dùng này")


def auto_restore_html(action: str, mention: str) -> str:
    mention = mention or "người dùng này"
    if action == "unrestrict":
        return AUTO_UNRESTRICT_HTML.format(mention=mention)
    return AUTO_UNBAN_HTML.format(mention=mention)


def missing_rights_html(mention: str) -> str:
    return MISSING_RIGHTS_HTML.format(mention=mention or "người dùng này")


def status_name(status) -> str:
    if status is None:
        return ""
    name = getattr(status, "name", None)
    if name:
        return str(name).upper()
    value = getattr(status, "value", None)
    if value is not None:
        return str(value).upper()
    return str(status).upper()


def is_listed(user_id, chat_ids: Iterable[int], global_ids: Iterable[int]) -> bool:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    return uid in set(int(x) for x in global_ids) or uid in set(int(x) for x in chat_ids)


NOTICE_DELETE_SECONDS = 10
RESTORE_DEDUPE_SECONDS = 20


def should_auto_restore(
    *,
    is_protected: bool,
    user_is_bot: bool,
    new_status,
    old_status=None,
    actor_is_self_bot: bool = False,
) -> Optional[str]:
    """Return 'unban', 'unrestrict', or None.

    Only a new restriction/ban by someone else is an incident. Ignore:
    the bot's own follow-up after it lifts a mute (often still RESTRICTED),
    updates that do not land on BANNED/RESTRICTED, and same-state repeats.
    """
    if not is_protected or user_is_bot or actor_is_self_bot:
        return None
    new = status_name(new_status)
    if new not in {"BANNED", "RESTRICTED"}:
        return None
    old = status_name(old_status)
    if old == new:
        return None
    return "unban" if new == "BANNED" else "unrestrict"


def should_dedupe_restore(last_ts, now: float, window: float = RESTORE_DEDUPE_SECONDS) -> bool:
    """True if this chat+user was already handled within the dedupe window."""
    if last_ts is None:
        return False
    try:
        return (float(now) - float(last_ts)) < float(window)
    except (TypeError, ValueError):
        return False


async def schedule_whitelist_autodel(client, msg, user_message=None) -> None:
    """Delete a whitelist notice after NOTICE_DELETE_SECONDS. Does not change global /autodel."""
    if msg is None or client is None:
        return
    try:
        from dorasuper.helper.autodel import schedule_autodel
        await schedule_autodel(
            client,
            msg,
            user_command_message=user_message,
            seconds=NOTICE_DELETE_SECONDS,
        )
    except Exception:
        pass


async def reply_and_autodel(reply_fn, text, *, client=None, user_message=None, **kwargs):
    """Send a whitelist reply and auto-delete it after 10s, skipping global /autodel."""
    kwargs["no_autodel"] = True
    sent = await reply_fn(text, **kwargs)
    app = client
    if app is None and user_message is not None:
        app = getattr(user_message, "_client", None)
    await schedule_whitelist_autodel(app, sent, user_message)
    return sent


def _norm_token(text: str) -> str:
    return unicodedata.normalize("NFC", (text or "").lower().strip())


def split_scope(args: list[str]) -> tuple[bool, list[str]]:
    """Detect a leading global-scope token (global / toancuc / toàn cục)."""
    if not args:
        return False, []
    first = _norm_token(args[0])
    if first in {"global", "toancuc", "toàncục"}:
        return True, list(args[1:])
    if first in {"toan", "toàn"} and len(args) > 1 and _norm_token(args[1]) in {"cuc", "cục"}:
        return True, list(args[2:])
    return False, list(args)
