"""Asia/Ho_Chi_Minh display helpers — VPS runs UTC so naive now() is wrong."""
from datetime import datetime, timezone, timedelta
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "tz",
    pathlib.Path(__file__).parent.parent / "dorasuper/helper/timezone.py",
)
tz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tz)


def test_now_vn_offset():
    now = tz.now_vn()
    assert now.tzinfo is not None
    # +07:00
    assert now.utcoffset() == timedelta(hours=7)


def test_format_vn_naive_assumed_utc():
    # 2026-11-09 07:48:00 UTC → 14:48:00 VN
    naive_utc = datetime(2026, 11, 9, 7, 48, 0)
    assert tz.format_vn(naive_utc, "%H:%M %d/%m/%Y") == "14:48 09/11/2026"
    aware = naive_utc.replace(tzinfo=timezone.utc)
    assert tz.format_vn(aware, tz.FMT_HM_DMY) == "14:48 09/11/2026"


def test_format_ts_vn():
    # epoch for 2026-11-09 07:48:00 UTC
    ts = datetime(2026, 11, 9, 7, 48, 0, tzinfo=timezone.utc).timestamp()
    assert tz.format_ts_vn(ts, "%H:%M %d/%m/%Y") == "14:48 09/11/2026"
    assert tz.format_ts_vn(ts, tz.FMT_DM_HM) == "09/11 14:48"
    assert tz.format_ts_vn(None) == "?"


def test_utc_timestamp_is_float():
    assert isinstance(tz.utc_timestamp(), float)


def test_to_vn_preserves_instant():
    utc = datetime(2026, 11, 9, 0, 0, 0, tzinfo=timezone.utc)
    vn = tz.to_vn(utc)
    assert vn.hour == 7
    assert vn.day == 9
