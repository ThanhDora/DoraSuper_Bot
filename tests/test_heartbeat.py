import importlib.util
import pathlib
import time

spec = importlib.util.spec_from_file_location(
    "heartbeat",
    pathlib.Path(__file__).parent.parent / "dorasuper/helper/heartbeat.py",
)
hb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hb)


def test_touch_and_read_heartbeat(tmp_path=None):
    base = pathlib.Path("/tmp/bot-watchdog-tests")
    base.mkdir(parents=True, exist_ok=True)
    path = str(base / "hb.heartbeat")
    try:
        pathlib.Path(path).unlink()
    except FileNotFoundError:
        pass
    hb.touch_heartbeat(path, now=1000.5)
    assert hb.read_heartbeat(path) == 1000.5
    # overwrite atomically
    hb.touch_heartbeat(path, now=2000.0)
    assert hb.read_heartbeat(path) == 2000.0
    assert hb.read_heartbeat(str(base / "missing")) is None


def test_default_path():
    assert hb.DEFAULT_PATH == "/run/bot-watchdog/dorasuper.heartbeat"
    assert hb.DEFAULT_INTERVAL == 60
    assert hb.DEFAULT_TIMEOUT == 30
