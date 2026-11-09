from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo

    VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:  # pragma: no cover
    VN_TZ = timezone(timedelta(hours=7))

UTC = timezone.utc

# Formats used in user-facing messages
FMT_HM_DMY = "%H:%M %d/%m/%Y"          # /up success, karma
FMT_HMS_DMY = "%H:%M:%S %d/%m/%Y"      # download_upload style
FMT_DM_HM = "%d/%m %H:%M"              # /up_banlist
FMT_DMY_HMS = "%d/%m/%Y %H:%M:%S"      # grup_tools join info


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_vn(dt: datetime | None) -> datetime | None:
    """Convert aware/naive datetime to Asia/Ho_Chi_Minh. Naive treated as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(VN_TZ)


def from_timestamp_vn(ts: float | int | None) -> datetime | None:
    """Unix timestamp (UTC) → aware VN datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).astimezone(VN_TZ)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def format_vn(dt: datetime | None, fmt: str = FMT_HM_DMY) -> str:
    """Format a datetime in Asia/Ho_Chi_Minh. Naive = UTC."""
    local = to_vn(dt)
    if local is None:
        return "?"
    return local.strftime(fmt)


def format_ts_vn(ts: float | int | None, fmt: str = FMT_HM_DMY) -> str:
    """Format a Unix timestamp (UTC seconds) in Asia/Ho_Chi_Minh."""
    local = from_timestamp_vn(ts)
    if local is None:
        return "?"
    return local.strftime(fmt)


def utc_timestamp() -> float:
    """Aware UTC now as Unix seconds for Mongo storage."""
    return now_utc().timestamp()
