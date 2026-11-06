import importlib.util
import pathlib
import re
import sys
import types

# Load helper without importing dorasuper/__init__ (which starts the client).
_ROOT = pathlib.Path(__file__).resolve().parents[1] / "dorasuper"
if "dorasuper" not in sys.modules:
    _pkg = types.ModuleType("dorasuper")
    _pkg.__path__ = [str(_ROOT)]
    sys.modules["dorasuper"] = _pkg


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


if "dorasuper.emoji" not in sys.modules:
    _load("dorasuper.emoji", _ROOT / "emoji.py")
pp = _load("dorasuper_pyro_progress_test", _ROOT / "helper" / "pyro_progress.py")


def test_time_formatter_vi():
    assert pp.time_formatter(210) == "3 phút 30 giây"
    assert pp.time_formatter(90061) == "1 ngày 1 giờ 1 phút 1 giây"
    assert pp.time_formatter(0) == ""


def test_humanbytes():
    assert pp.humanbytes(0) == ""
    assert pp.humanbytes(1536) == "1.5 KiB"
    assert pp.humanbytes(86.53 * 1024 * 1024) == "86.53 MiB"


def test_format_progress():
    mb = 1024 * 1024
    html = pp.format_progress_html(33 * mb, 86.53 * mb, 80, 5, "TITLE")
    assert html.startswith("TITLE")
    for label in ("Tiến trình", "Đã tải", "Tốc độ", "Máy chủ DC", "Còn lại"):
        assert label in html
    assert html.count("<tg-emoji") >= 7
    bar = re.search(r"\[([█░]+)\]", html).group(1)
    assert len(bar) == 20 and bar.count("█") == 7
    assert "Máy chủ DC:</b> 5" in html


def test_zero_safe():
    html = pp.format_progress_html(0, 0, 0, None, "T")
    assert "0.0%" in html and "đang tính" in html and "DC:</b> -" in html


def test_throttle():
    store = {}
    assert pp.should_update_progress("k", 1, 10, now=100, store=store)
    assert not pp.should_update_progress("k", 2, 10, now=101, store=store)
    assert pp.should_update_progress("k", 3, 10, now=103.1, store=store)
    assert pp.should_update_progress("k", 10, 10, now=103.2, store=store)
