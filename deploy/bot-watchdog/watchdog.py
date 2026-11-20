#!/usr/bin/env python3
"""External hang watchdog for dorasuper, misyou, and testflight systemd units.

Does not start a Telegram client. Reads heartbeat files written by each bot,
optionally inspects Telegram TCP state, and runs ``systemctl restart`` when a
service looks hung. Rate-limits restarts and can notify via Bot API HTTP.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable, Optional

STATE_DIR = os.environ.get("BOT_WATCHDOG_STATE", "/var/lib/bot-watchdog")
HEARTBEAT_DIR = os.environ.get("BOT_WATCHDOG_HEARTBEAT_DIR", "/run/bot-watchdog")
STALE_SEC = int(os.environ.get("BOT_WATCHDOG_STALE_SEC", "300"))
GRACE_SEC = int(os.environ.get("BOT_WATCHDOG_GRACE_SEC", "300"))
MAX_RESTARTS = int(os.environ.get("BOT_WATCHDOG_MAX_RESTARTS", "3"))
RESTART_WINDOW = int(os.environ.get("BOT_WATCHDOG_RESTART_WINDOW", "1800"))
NOTIFY_ADMIN_FALLBACK = 5341455835

TELEGRAM_NETS = (
    ipaddress.ip_network("91.108.0.0/16"),
    ipaddress.ip_network("149.154.160.0/20"),
)

SERVICES = {
    "dorasuper": {
        "unit": "dorasuper.service",
        "heartbeat": os.path.join(HEARTBEAT_DIR, "dorasuper.heartbeat"),
        "env_file": "/opt/DoraSuper_Bot/config.env",
        "token_keys": ("BOT_TOKEN",),
        "notify_keys": ("LOG_CHANNEL", "SUDO"),
    },
    "misyou": {
        "unit": "misyou.service",
        "heartbeat": os.path.join(HEARTBEAT_DIR, "misyou.heartbeat"),
        "env_file": "/opt/misyou_iBot/.env",
        "token_keys": ("BOT_TOKEN",),
        "notify_keys": ("LOG_CHANNEL", "ADMIN"),
    },
    "testflight": {
        "unit": "testflight.service",
        "heartbeat": os.path.join(HEARTBEAT_DIR, "testflight.heartbeat"),
        "env_file": "/opt/testflight_checker/.env",
        "token_keys": ("BOT_TOKEN",),
        "notify_keys": ("ADMIN_ID", "ADMIN"),
    },
}


def log(msg: str) -> None:
    print(msg, flush=True)
    try:
        subprocess.run(
            ["systemd-cat", "-t", "bot-watchdog", "-p", "info"],
            input=msg + "\n",
            text=True,
            check=False,
            timeout=5,
        )
    except Exception:
        pass


def read_env_file(path: str) -> dict:
    """Parse KEY=VALUE env file. Values are never logged."""
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                    val = val[1:-1]
                out[key] = val
    except OSError:
        return {}
    return out


def parse_id_list(*values: str) -> list[int]:
    ids = []
    for value in values:
        if not value:
            continue
        for part in value.replace(",", " ").split():
            try:
                ids.append(int(part))
            except ValueError:
                continue
    # unique, stable
    seen = set()
    out = []
    for i in ids:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def heartbeat_age(path: str, now: Optional[float] = None) -> Optional[float]:
    """Seconds since heartbeat timestamp, or None if missing/invalid."""
    now = time.time() if now is None else now
    try:
        with open(path, "r", encoding="ascii") as fh:
            ts = float(fh.read().strip())
    except (OSError, ValueError):
        return None
    return max(0.0, now - ts)


def is_stale(age: Optional[float], stale_sec: int = STALE_SEC) -> bool:
    return age is None or age > stale_sec


def is_telegram_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in TELEGRAM_NETS)


def parse_peer_ip(peer: str) -> Optional[str]:
    """Extract IP from ``ss`` local/peer column (ip:port or [ipv6]:port)."""
    if not peer:
        return None
    if peer.startswith("["):
        end = peer.find("]")
        if end > 1:
            return peer[1:end]
        return None
    if ":" not in peer:
        return None
    return peer.rsplit(":", 1)[0]


def classify_telegram_sockets(ss_lines: Iterable[str], pid: int) -> dict:
    """Count Telegram ESTAB / CLOSE-WAIT sockets belonging to pid from ``ss -tnp`` output."""
    counts = {"estab": 0, "close_wait": 0, "other": 0, "total_tg": 0}
    needle = f"pid={pid}"
    for raw in ss_lines:
        line = raw.strip()
        if needle not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        state = parts[0].upper().replace("-", "_")
        peer_ip = parse_peer_ip(parts[4] if len(parts) > 4 else "")
        if not peer_ip or not is_telegram_ip(peer_ip):
            continue
        counts["total_tg"] += 1
        if state == "ESTAB" or state == "ESTABLISHED":
            counts["estab"] += 1
        elif state == "CLOSE_WAIT":
            counts["close_wait"] += 1
        else:
            counts["other"] += 1
    return counts


def telegram_dead(counts: dict) -> bool:
    """True when we see Telegram CLOSE-WAIT and no established Telegram socket."""
    return counts.get("close_wait", 0) > 0 and counts.get("estab", 0) == 0


def load_restart_times(state_path: str, name: str) -> list[float]:
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        times = data.get(name) or []
        return [float(x) for x in times]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []


def save_restart_times(state_path: str, name: str, times: list[float]) -> None:
    directory = os.path.dirname(state_path) or "."
    os.makedirs(directory, exist_ok=True)
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        data = {}
    data[name] = times
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
        fh.write("\n")
    os.replace(tmp, state_path)


def rate_limited(times: list[float], now: float, max_restarts: int = MAX_RESTARTS, window: int = RESTART_WINDOW) -> tuple[bool, list[float]]:
    recent = [t for t in times if now - t < window]
    return len(recent) >= max_restarts, recent


def record_restart(times: list[float], now: float, window: int = RESTART_WINDOW) -> list[float]:
    """Prune expired restart timestamps and append this restart."""
    _, recent = rate_limited(times, now, window=window)
    recent.append(now)
    return recent


def decide(
    *,
    active: bool,
    uptime_sec: Optional[float],
    age: Optional[float],
    sockets: Optional[dict] = None,
    recent_restarts: Optional[list[float]] = None,
    now: Optional[float] = None,
    stale_sec: int = STALE_SEC,
    grace_sec: int = GRACE_SEC,
    max_restarts: int = MAX_RESTARTS,
    window: int = RESTART_WINDOW,
) -> dict:
    """Pure decision. action is skip | restart | rate_limited."""
    now = time.time() if now is None else now
    recent = list(recent_restarts or [])
    limited, recent = rate_limited(recent, now, max_restarts, window)
    result = {
        "action": "skip",
        "reason": "",
        "stale": is_stale(age, stale_sec),
        "age": age,
        "telegram_dead": bool(sockets and telegram_dead(sockets)),
        "rate_limited": False,
    }
    if not active:
        result["reason"] = "service not active"
        return result
    if uptime_sec is not None and uptime_sec < grace_sec:
        result["reason"] = f"within grace period ({uptime_sec:.0f}s < {grace_sec}s)"
        return result
    if not result["stale"]:
        result["reason"] = f"heartbeat fresh ({age:.0f}s)"
        return result
    age_txt = "missing" if age is None else f"{age:.0f}s old"
    reason = f"heartbeat stale ({age_txt})"
    if result["telegram_dead"]:
        reason += "; telegram socket CLOSE-WAIT with no ESTAB"
    if limited:
        result["action"] = "rate_limited"
        result["rate_limited"] = True
        result["reason"] = reason + f"; rate limited ({len(recent)}/{max_restarts} in {window // 60}m)"
        return result
    result["action"] = "restart"
    result["reason"] = reason
    return result


def _systemctl(*args: str, timeout: int = 20) -> str:
    proc = subprocess.run(
        ["systemctl", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return (proc.stdout or "").strip()


def service_active(unit: str) -> bool:
    return _systemctl("is-active", unit) == "active"


def service_pid(unit: str) -> int:
    try:
        return int(_systemctl("show", unit, "-p", "MainPID", "--value") or "0")
    except ValueError:
        return 0


def service_uptime_sec(unit: str, now: Optional[float] = None) -> Optional[float]:
    now = time.time() if now is None else now
    raw = _systemctl("show", unit, "-p", "ExecMainStartTimestampMonotonic", "-p", "ActiveEnterTimestampMonotonic")
    # fallback: ActiveEnterTimestamp
    mon = None
    for line in raw.splitlines():
        if line.startswith("ExecMainStartTimestampMonotonic="):
            try:
                mon = int(line.split("=", 1)[1] or "0")
            except ValueError:
                mon = None
    if not mon:
        ts = _systemctl("show", unit, "-p", "ActiveEnterTimestamp", "--value")
        if not ts or ts == "n/a":
            return None
        # try parse via date
        try:
            proc = subprocess.run(
                ["date", "-u", "+%s", "-d", ts],
                capture_output=True, text=True, timeout=5, check=False,
            )
            started = int((proc.stdout or "0").strip() or "0")
            if started:
                return max(0.0, now - started)
        except Exception:
            return None
        return None
    # monotonic usec from boot
    try:
        with open("/proc/uptime", "r") as fh:
            uptime = float(fh.read().split()[0])
        start_from_boot = mon / 1_000_000.0
        return max(0.0, uptime - start_from_boot)
    except (OSError, ValueError):
        return None


def collect_ss() -> list[str]:
    try:
        proc = subprocess.run(
            ["ss", "-tnp"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return (proc.stdout or "").splitlines()
    except Exception:
        return []


def notify_chats(token: str, chat_ids: list[int], text: str) -> None:
    if not token or not chat_ids:
        return
    for chat_id in chat_ids:
        try:
            body = urllib.parse.urlencode(
                {"chat_id": str(chat_id), "text": text}
            ).encode("utf-8")
            url = "https://api.telegram.org/bot{}/sendMessage".format(token)
            req = urllib.request.Request(url, data=body, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            log(f"notify failed for chat_id={chat_id}")


def notify_for_service(spec: dict, text: str) -> None:
    env = read_env_file(spec["env_file"])
    token = ""
    for key in spec.get("token_keys") or ("BOT_TOKEN",):
        if env.get(key):
            token = env[key]
            break
    if not token:
        log(f"notify skipped for {spec['unit']}: no bot token in env file")
        return
    values = [env.get(k, "") for k in spec.get("notify_keys") or ()]
    chat_ids = parse_id_list(*values)
    if not chat_ids:
        chat_ids = [NOTIFY_ADMIN_FALLBACK]
    notify_chats(token, chat_ids, text)


def restart_unit(unit: str) -> bool:
    proc = subprocess.run(
        ["systemctl", "restart", unit],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        log(f"systemctl restart {unit} failed: {err[-1] if err else proc.returncode}")
        return False
    return True


def check_one(name: str, spec: dict, *, dry_run: bool, now: Optional[float] = None, ss_lines: Optional[list[str]] = None) -> dict:
    unit = spec["unit"]
    now = time.time() if now is None else now
    active = service_active(unit)
    uptime = service_uptime_sec(unit, now=now) if active else None
    age = heartbeat_age(spec["heartbeat"], now=now)
    pid = service_pid(unit) if active else 0
    sockets = None
    if pid:
        sockets = classify_telegram_sockets(ss_lines if ss_lines is not None else collect_ss(), pid)
    state_path = os.path.join(STATE_DIR, "restarts.json")
    recent = load_restart_times(state_path, name)
    decision = decide(
        active=active,
        uptime_sec=uptime,
        age=age,
        sockets=sockets,
        recent_restarts=recent,
        now=now,
    )
    decision["service"] = name
    decision["unit"] = unit
    decision["pid"] = pid
    decision["sockets"] = sockets
    log(
        f"{name}: action={decision['action']} reason={decision['reason']} "
        f"pid={pid} sockets={sockets}"
    )
    if decision["action"] == "rate_limited":
        if not dry_run:
            notify_for_service(
                spec,
                f"Watchdog: {unit} bị treo (heartbeat quá hạn) nhưng đã đạt giới hạn "
                f"khởi động lại ({MAX_RESTARTS} lần / {RESTART_WINDOW // 60} phút). Cần kiểm tra thủ công.",
            )
        return decision
    if decision["action"] != "restart":
        return decision
    if dry_run:
        log(f"{name}: dry-run, would restart {unit}")
        return decision
    log(f"{name}: restarting {unit} — {decision['reason']}")
    ok = restart_unit(unit)
    if ok:
        recent = record_restart(recent, now)
        save_restart_times(state_path, name, recent)
        try:
            notify_for_service(
                spec,
                f"Watchdog đã khởi động lại {unit}. Lý do: {decision['reason']}.",
            )
        except Exception as exc:
            # Do not log the exception text; it might include a request URL with the token.
            log(f"{name}: notify error: {type(exc).__name__}")
    return decision


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Restart hung DoraSuper/misyou/testflight bots")
    parser.add_argument("--dry-run", action="store_true", help="Decide and log, do not restart or notify")
    parser.add_argument("--service", choices=list(SERVICES), help="Check only this service")
    args = parser.parse_args(argv)
    os.makedirs(HEARTBEAT_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    names = [args.service] if args.service else list(SERVICES)
    ss_lines = collect_ss()
    now = time.time()
    for name in names:
        try:
            check_one(name, SERVICES[name], dry_run=args.dry_run, now=now, ss_lines=ss_lines)
        except Exception as exc:
            log(f"{name}: watchdog error: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
