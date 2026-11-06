# Telegram custom emoji

Messages now use official `<tg-emoji emoji-id="ID">ALT</tg-emoji>` syntax.
The project-local parser turns this into Telegram's `messageEntityCustomEmoji`
with UTF-16 offsets. Existing legacy `<emoji id="ID">ALT</emoji>` input (including
stored notes) is still supported. Existing emoji IDs/fallbacks are unchanged.

Buttons use `InlineKeyboardButton(..., icon_custom_emoji_id="ID")`. Existing
button templates can keep using `EMOJI_FMT_BTN`: the patched constructor extracts
the first tagged ID, removes all custom-emoji tags/fallbacks from the label, and
sends `KeyboardButtonStyle(icon=ID)` separately. Callback data, URLs, inline
queries, login links and web-app actions are not changed. Plain Unicode labels
without a tagged/custom icon remain unchanged. Icon-only templates use a
non-empty invisible label because Telegram forbids empty button text.

The existing pyrofork dependency is retained: the checked upstream button/HTML
implementations did not expose these new fields/tags. No site-packages edits or
client/API-layer-wide upgrade is needed. `dorasuper/tg_keyboard.py` contains the
verified TL constructor IDs/field ordering from Telegram's published schema.
Only styled outgoing buttons use those constructors; ordinary buttons keep the
installed library's original constructors. Existing old-layer response
constructors stay registered. A future full client-layer upgrade should be
reviewed independently rather than changing the layer number alone.

`USE_PREMIUM_EMOJI=false` disables custom entities and button icons at the parser,
button writer and request boundary. Messages retain their Unicode alternatives.
For known emoji rejection RPC errors, the central request boundary retries once
without custom entities/icons, preserving ordinary formatting, button actions
and the request's random ID. It does not retry arbitrary/network errors. A retry
that also fails is propagated normally. High-level `reply_safe`/`edit_safe` also
provide Unicode/plain-icon fallback.

## Offline verification (does not start a bot)

```sh
PYTHONDONTWRITEBYTECODE=1 DORASUPER_OFFLINE=1 ./venv/bin/python -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 DORASUPER_OFFLINE=1 ./venv/bin/python -c 'import dorasuper; from dorasuper.tg_emoji import split_button; print("offline import OK")'
```

The original package starts clients at import time. `DORASUPER_OFFLINE=1` is an
explicit test-only guard: it skips config loading, database/client construction
and startup, while installing the emoji compatibility layer. Do not set it when
running the actual bot. Plugin pure-helper tests load only selected definitions,
not handlers or databases.

No live Telegram send has been tested. Custom-emoji permissions are enforced by
Telegram (bot-owner Premium/eligible contexts or Fragment extra username rules),
not by this patch; upgrading a library cannot grant these permissions. Client
version and animation settings may affect rendering. The alt emoji is required
by Telegram and is a text fallback, not a promise of animated rendering on all
clients. Ask Telegram for the actual custom-emoji document's alt when adding a
new ID; do not invent IDs or fallback mappings.

Sources:
- https://core.telegram.org/schema/json (constructor IDs/flags; checked 2026-11-06)
- https://core.telegram.org/constructor/keyboardButtonStyle
- https://core.telegram.org/bots/api#inlinekeyboardbutton
- https://core.telegram.org/bots/api#html-style
