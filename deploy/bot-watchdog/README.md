# Bot hang watchdog

Restarts DoraSuper, misyou, and testflight when a process stays up but stops handling Telegram (the Nov 14 / Nov 20 DoraSuper hang: systemd still `active`, MTProto socket `CLOSE-WAIT`, busy loop, no logs, SIGTERM ignored).

## Design

1. **In-process heartbeat** (each bot, no second client):
   - DoraSuper and misyou: an asyncio task every 60s runs an MTProto `Ping` (not cached `get_me()`) with a 30s timeout and, on success, writes `/run/bot-watchdog/<name>.heartbeat`.
   - testflight: the existing 60s watch loop touches the same style of file when a cycle finishes (even if the Apple request failed). If the Node event loop hangs, the file goes stale.
2. **systemd timer** (`bot-watchdog.timer`) every 1 minute runs `/opt/bot-watchdog/watchdog.py`.
3. The script restarts a unit with `systemctl restart` only if all of these hold:
   - the service is `active`
   - it has been running longer than a **5 minute grace** period after start
   - the heartbeat is **missing or older than 5 minutes**
   - fewer than **3 restarts in 30 minutes** (otherwise it logs and notifies, then waits)
4. Telegram `CLOSE-WAIT` with no `ESTAB` to Telegram DCs is logged as extra evidence; the stale heartbeat is the primary trigger (a dead event loop never refreshes the file).
5. **TimeoutStopSec=15s** drop-ins on the three bot units so a process that ignores SIGTERM is SIGKILLed quickly (the Nov 20 hang needed SIGKILL after the default 90s).
6. Optional notify: HTTP `sendMessage` to the bot’s admin / log chat using the token in that bot’s env file. Tokens are never logged.

## Install (VPS)

```bash
install -d /opt/bot-watchdog /run/bot-watchdog /var/lib/bot-watchdog
install -m 755 deploy/bot-watchdog/watchdog.py /opt/bot-watchdog/watchdog.py
cp deploy/bot-watchdog/README.md /opt/bot-watchdog/
cp deploy/bot-watchdog/units/bot-watchdog.service /etc/systemd/system/
cp deploy/bot-watchdog/units/bot-watchdog.timer /etc/systemd/system/
cp deploy/bot-watchdog/units/bot-watchdog.conf /etc/tmpfiles.d/
systemd-tmpfiles --create /etc/tmpfiles.d/bot-watchdog.conf
for s in dorasuper misyou testflight; do
  mkdir -p /etc/systemd/system/${s}.service.d
  cp deploy/bot-watchdog/units/stop-timeout.conf /etc/systemd/system/${s}.service.d/stop-timeout.conf
done
systemctl daemon-reload
systemctl enable --now bot-watchdog.timer
```

After deploying heartbeat code, restart each bot once so the loop starts.

## Commands

```bash
# Watchdog timer and last runs
systemctl status bot-watchdog.timer bot-watchdog.service
journalctl -u bot-watchdog.service -u bot-watchdog.timer -t bot-watchdog -n 50 --no-pager

# Heartbeat files (unix timestamp, should refresh about every 60s)
cat /run/bot-watchdog/dorasuper.heartbeat
stat /run/bot-watchdog/*.heartbeat

# Decide without restarting
python3 /opt/bot-watchdog/watchdog.py --dry-run
python3 /opt/bot-watchdog/watchdog.py --dry-run --service dorasuper

# Restart history (rate limit)
cat /var/lib/bot-watchdog/restarts.json
```

Environment overrides: `BOT_WATCHDOG_STALE_SEC` (default 300), `BOT_WATCHDOG_GRACE_SEC` (300), `BOT_WATCHDOG_MAX_RESTARTS` (3), `BOT_WATCHDOG_RESTART_WINDOW` (1800), `BOT_WATCHDOG_STATE`, `BOT_WATCHDOG_HEARTBEAT_DIR`. Bots honor `BOT_HEARTBEAT_PATH`.
