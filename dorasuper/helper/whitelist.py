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


def should_auto_restore(*, is_protected: bool, user_is_bot: bool, new_status) -> Optional[str]:
    """Return 'unban', 'unrestrict', or None.

    Triggered whenever a protected (non-bot) user becomes banned or restricted,
    including when the actor is this bot (safety net). After a successful
    restore the follow-up update is MEMBER/LEFT, so this will not loop.
    """
    if not is_protected or user_is_bot:
        return None
    name = status_name(new_status)
    if name == "BANNED":
        return "unban"
    if name == "RESTRICTED":
        return "unrestrict"
    return None


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
