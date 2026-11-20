import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "bot_watchdog",
    pathlib.Path(__file__).parent.parent / "deploy/bot-watchdog/watchdog.py",
)
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)


def test_is_telegram_ip():
    assert wd.is_telegram_ip("91.108.56.130")
    assert wd.is_telegram_ip("149.154.166.110")
    assert not wd.is_telegram_ip("8.8.8.8")
    assert not wd.is_telegram_ip("162.159.133.234")  # Cloudflare, not a TG DC


def test_classify_close_wait_and_estab():
    lines = [
        "ESTAB 0 0 10.0.0.1:1 8.8.8.8:443 users:((\"py\",pid=10,fd=1))",
        "CLOSE-WAIT 1 0 10.0.0.1:2 91.108.56.130:443 users:((\"py\",pid=99,fd=2))",
        "ESTAB 0 0 10.0.0.1:3 149.154.166.110:443 users:((\"py\",pid=99,fd=3))",
    ]
    both = wd.classify_telegram_sockets(lines, 99)
    assert both == {"estab": 1, "close_wait": 1, "other": 0, "total_tg": 2}
    assert wd.telegram_dead(both) is False
    only_cw = wd.classify_telegram_sockets(
        ["CLOSE-WAIT 1 0 10.0.0.1:2 91.108.56.130:443 users:((\"py\",pid=99,fd=2))"],
        99,
    )
    assert wd.telegram_dead(only_cw) is True
    assert wd.classify_telegram_sockets(lines, 10)["total_tg"] == 0


def test_decide_grace_and_fresh():
    d = wd.decide(active=True, uptime_sec=30, age=None, now=1000)
    assert d["action"] == "skip"
    assert "grace" in d["reason"]
    d = wd.decide(active=True, uptime_sec=400, age=20, now=1000)
    assert d["action"] == "skip"
    assert "fresh" in d["reason"]
    d = wd.decide(active=False, uptime_sec=400, age=999, now=1000)
    assert d["action"] == "skip"


def test_decide_stale_restarts():
    d = wd.decide(active=True, uptime_sec=400, age=400, now=10_000)
    assert d["action"] == "restart"
    assert "stale" in d["reason"]
    d = wd.decide(
        active=True, uptime_sec=400, age=None, now=10_000,
        sockets={"estab": 0, "close_wait": 1, "other": 0, "total_tg": 1},
    )
    assert d["action"] == "restart"
    assert "CLOSE-WAIT" in d["reason"]


def test_decide_rate_limit():
    now = 10_000.0
    recent = [now - 60, now - 120, now - 180]
    d = wd.decide(
        active=True, uptime_sec=400, age=400, now=now, recent_restarts=recent,
    )
    assert d["action"] == "rate_limited"
    limited, kept = wd.rate_limited(recent, now)
    assert limited is True
    assert len(kept) == 3
    limited, kept = wd.rate_limited([now - 2000], now)
    assert limited is False
    assert kept == []


def test_parse_id_list():
    assert wd.parse_id_list("5341455835 1", "-10042") == [5341455835, 1, -10042]
