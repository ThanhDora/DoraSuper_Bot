"""Đăng bài lên kênh: parse App Store, render ảnh, dựng caption (không phụ thuộc pyrogram)."""
from __future__ import annotations

import html
import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ALLOWED_EXTENSIONS = {
    ".ipa", ".tipa", ".deb", ".dylib", ".zip", ".7z", ".rar", ".tar", ".gz", ".xz",
}

DOWNLOAD_BUTTON_TEXT = "Tải file"
CHANNEL_BUTTON_TEXT = "Kênh"
GROUP_BUTTON_TEXT = "Nhóm chat"

_CLEAR_LINK_WORDS = frozenset({
    "off", "clear", "none", "xoa", "xoá", "xóa", "huy", "huỷ", "hủy",
})


def build_upfile_url(bot_username: str, token: str) -> str:
    user = (bot_username or "").lstrip("@").strip()
    tok = (token or "").strip()
    return f"https://t.me/{user}?start=upfile_{tok}"


def is_clear_link_arg(raw: str) -> bool:
    text = (raw or "").strip().lower()
    return text in _CLEAR_LINK_WORDS


def normalize_telegram_link(raw: str) -> str | None:
    """Chuẩn hóa @user / t.me/... / invite thành https://t.me/... ; None nếu không hợp lệ."""
    text = (raw or "").strip()
    if not text:
        return None
    if is_clear_link_arg(text):
        return None
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    lower = text.lower()
    if lower.startswith("http://"):
        text = "https://" + text[7:]
        lower = text.lower()
    if text.startswith("@"):
        user = text[1:].strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{4,}", user):
            return None
        return f"https://t.me/{user}"
    if lower.startswith("tg://resolve"):
        m = re.search(r"[?&]domain=([A-Za-z0-9_]+)", text, re.I)
        if not m:
            return None
        return f"https://t.me/{m.group(1)}"
    if lower.startswith("t.me/") or lower.startswith("telegram.me/"):
        text = "https://" + text
        lower = text.lower()
    if not (lower.startswith("https://t.me/") or lower.startswith("https://telegram.me/")):
        # Bare username without @
        if re.fullmatch(r"[A-Za-z0-9_]{4,}", text):
            return f"https://t.me/{text}"
        return None
    # Force https://t.me/
    path = text.split("://", 1)[1]
    path = path.split("/", 1)[1] if "/" in path else ""
    path = path.strip()
    if not path:
        return None
    # invite (+xxx or joinchat/xxx) or username(/...)
    if path.startswith("+") or path.lower().startswith("joinchat/"):
        return f"https://t.me/{path.split('?', 1)[0].split('#', 1)[0]}"
    user = path.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_]{4,}", user):
        return None
    return f"https://t.me/{user}"


def build_download_keyboard_botapi(
    bot_username: str,
    token: str,
    *,
    channel_url: str | None = None,
    group_url: str | None = None,
) -> dict:
    """Inline keyboard Bot API: hàng 1 Tải file; hàng 2 Kênh | Nhóm chat (nếu có)."""
    rows = [[
        {"text": DOWNLOAD_BUTTON_TEXT, "url": build_upfile_url(bot_username, token)},
    ]]
    link_row = []
    if channel_url:
        link_row.append({"text": CHANNEL_BUTTON_TEXT, "url": channel_url})
    if group_url:
        link_row.append({"text": GROUP_BUTTON_TEXT, "url": group_url})
    if link_row:
        rows.append(link_row)
    return {"inline_keyboard": rows}


def reply_markup_to_botapi(reply_markup) -> dict | None:
    """Đổi InlineKeyboardMarkup (Pyrogram) hoặc dict sẵn sang payload reply_markup Bot API."""
    if reply_markup is None:
        return None
    if isinstance(reply_markup, dict):
        if "inline_keyboard" in reply_markup:
            return reply_markup
        return None
    rows_out = []
    for row in getattr(reply_markup, "inline_keyboard", None) or []:
        buttons = []
        for btn in row:
            if isinstance(btn, dict):
                item = {"text": btn.get("text") or ""}
                if btn.get("url"):
                    item["url"] = btn["url"]
                elif btn.get("callback_data") is not None:
                    item["callback_data"] = btn["callback_data"]
                buttons.append(item)
                continue
            item = {"text": getattr(btn, "text", None) or ""}
            url = getattr(btn, "url", None)
            cb = getattr(btn, "callback_data", None)
            if url:
                item["url"] = url
            elif cb is not None:
                item["callback_data"] = cb
            buttons.append(item)
        rows_out.append(buttons)
    return {"inline_keyboard": rows_out}


JOINED_BUTTON_TEXT = "Đã tham gia, tải file"
BLOCKQUOTE_FEATURES_OPEN = "<blockquote expandable>"


def _status_name(status) -> str:
    if status is None:
        return ""
    if hasattr(status, "name"):
        return str(status.name).lower()
    text = str(status)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.lower()


def membership_is_joined(status, is_member=None) -> bool:
    """True nếu được coi là đang trong chat (OWNER/ADMIN/MEMBER/RESTRICTED+is_member)."""
    name = _status_name(status)
    if name in ("owner", "administrator", "member"):
        return True
    if name == "restricted":
        return bool(is_member)
    return False


def membership_is_banned(status) -> bool:
    """Chỉ BANNED/KICKED (Telegram đã cấm). LEFT / never-joined không phải banned."""
    name = _status_name(status)
    return name in ("banned", "kicked")


def membership_check_result(status, is_member=None) -> str:
    """Trả 'joined' | 'missing' | 'banned' từ status get_chat_member.

    LEFT / RESTRICTED(!is_member) / unknown non-member → missing (hiện join prompt).
    BANNED/KICKED → banned (cần kết hợp Mongo ở tầng trên).
    """
    if membership_is_banned(status):
        return "banned"
    if membership_is_joined(status, is_member):
        return "joined"
    return "missing"


def should_autoban_on_leave(
    *,
    old_status,
    new_status,
    user_is_bot: bool = False,
    user_is_sudo: bool = False,
    left_by_admin: bool = False,
    self_leave: bool = False,
    old_is_member=None,
) -> bool:
    """True chỉ khi user TỰ rời: MEMBER/RESTRICTED(is_member) → LEFT.

    Bắt buộc self_leave=True (from_user.id == user.id). Không ban khi from_user
    thiếu/admin kick / bot / sudo / never-joined (old LEFT) / download-gate.
    """
    if user_is_bot or user_is_sudo or left_by_admin or not self_leave:
        return False
    old_name = _status_name(old_status)
    new_name = _status_name(new_status)
    if new_name != "left":
        return False
    if old_name == "member":
        return True
    if old_name == "restricted":
        # chỉ khi trước đó đang là thành viên bị hạn chế, không phải chờ duyệt
        return bool(old_is_member) if old_is_member is not None else True
    return False


def join_gate_block_kind(*, tg_banned: bool, has_leave_ban_record: bool) -> str | None:
    """None = không block kiểu ban; 'leave_ban' | 'admin_ban'."""
    if tg_banned and has_leave_ban_record:
        return "leave_ban"
    if tg_banned and not has_leave_ban_record:
        return "admin_ban"
    if has_leave_ban_record and not tg_banned:
        # record cũ nhưng TG không còn BANNED → không hiện leave-ban; để join prompt / deliver xử lý
        return None
    return None


def should_clear_leave_ban_on_unban(*, old_status, new_status) -> bool:
    """Admin unban: BANNED -> LEFT (chưa vào lại) hoặc -> MEMBER."""
    old_name = _status_name(old_status)
    new_name = _status_name(new_status)
    if old_name not in ("banned", "kicked"):
        return False
    return new_name in ("left", "member", "restricted", "administrator", "owner")


def parse_promo_link_args(raw: str) -> dict:
    """Parse arg của /up_link_*: action show|clear|here|set; url; chat_id."""
    text = (raw or "").strip()
    if not text:
        return {"action": "show", "url": None, "chat_id": None}
    if is_clear_link_arg(text):
        return {"action": "clear", "url": None, "chat_id": None}
    lower = text.lower()
    if lower in ("here", "đây", "day"):
        return {"action": "here", "url": None, "chat_id": None}
    parts = text.split()
    chat_id = None
    url_part = text
    if len(parts) >= 2:
        # last token may be chat id
        maybe = parts[-1]
        if re.fullmatch(r"-?\d{6,}", maybe):
            chat_id = int(maybe)
            url_part = " ".join(parts[:-1]).strip() or None
    if url_part and re.fullmatch(r"-?\d{6,}", url_part.strip()):
        return {"action": "set", "url": None, "chat_id": int(url_part.strip())}
    url = normalize_telegram_link(url_part) if url_part else None
    if url or chat_id is not None:
        return {"action": "set", "url": url, "chat_id": chat_id}
    return {"action": "invalid", "url": None, "chat_id": None}



def public_username_from_tme_url(url: str) -> str | None:
    """Lấy @username công khai từ https://t.me/user; None nếu invite/+ hoặc không parse được."""
    text = (url or "").strip()
    if not text:
        return None
    lower = text.lower()
    if "/+" in lower or "joinchat/" in lower:
        return None
    m = re.search(r"(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,})", text, re.I)
    if not m:
        return None
    user = m.group(1)
    if user.lower() in ("c", "joinchat", "addstickers", "share", "s"):
        return None
    return user


def evaluate_join_gate_decision(configured: list[str], results: dict[str, str]) -> dict:
    """Fail-closed khi đã cấu hình link.

    results[kind] in {"joined","missing","banned","error"}.
    Nếu không cấu hình gì → ok (không chặn).
    Có cấu hình mà error/missing/banned → không ok (không gửi file).
    """
    configured = [k for k in (configured or []) if k]
    if not configured:
        return {
            "ok": True,
            "banned": False,
            "missing": [],
            "errors": [],
            "checkable": 0,
        }
    banned = any(results.get(k) == "banned" for k in configured)
    missing = [k for k in configured if results.get(k) == "missing"]
    errors = [k for k in configured if results.get(k) in (None, "error") or k not in results]
    # also treat unknown as error
    for k in configured:
        if results.get(k) not in ("joined", "missing", "banned", "error"):
            if k not in errors:
                errors.append(k)
    if banned:
        return {
            "ok": False,
            "banned": True,
            "missing": missing,
            "errors": errors,
            "checkable": len(configured) - len(errors),
        }
    if missing or errors:
        return {
            "ok": False,
            "banned": False,
            "missing": missing,
            "errors": errors,
            "checkable": len(configured) - len(errors),
        }
    return {
        "ok": True,
        "banned": False,
        "missing": [],
        "errors": [],
        "checkable": len(configured),
    }


def build_join_gate_keyboard_botapi(
    token: str,
    *,
    channel_url: str | None = None,
    group_url: str | None = None,
) -> dict:
    """Nút join + callback xác nhận tải (không có URL Tải file để tránh bypass)."""
    rows = []
    link_row = []
    if channel_url:
        link_row.append({"text": CHANNEL_BUTTON_TEXT, "url": channel_url})
    if group_url:
        link_row.append({"text": GROUP_BUTTON_TEXT, "url": group_url})
    if link_row:
        rows.append(link_row)
    rows.append([{"text": JOINED_BUTTON_TEXT, "callback_data": f"upjoin_{token}"}])
    return {"inline_keyboard": rows}


APPSTORE_ID_RE = re.compile(
    r"(?:(?:apps|itunes)\.apple\.com/.+?/id|(?:apps|itunes)\.apple\.com/app/id)(\d+)"
    r"|[?&]id=(\d+)"
    r"|apple\.com/.*/id(\d+)",
    re.IGNORECASE,
)

_FEATURE_RULES = (
    (re.compile(r"vô hạn|unlimited|infinite|tiền|vàng|gold|coin|gem|kim cương|\bkc\b", re.I), "gift"),
    (re.compile(r"bất tử|immortal|god\s*mode|không chết|bat tu", re.I), "shield"),
    (re.compile(r"mod\s*menu|\bmenu\b", re.I), "gear"),
    (re.compile(r"tốc độ|toc do|speed|nhanh", re.I), "rocket"),
    (re.compile(r"bypass|anti[-\s]?ban|jailbreak", re.I), "lock"),
    (re.compile(r"aim|headshot|aimbot", re.I), "dart"),
    (re.compile(r"map|radar|minimap", re.I), "pin"),
    (re.compile(r"\bvip\b|premium", re.I), "crown"),
    (re.compile(r"hack|cheat|mod\b", re.I), "fire"),
    (re.compile(r"skin|nhân vật|nhan vat", re.I), "party"),
)


def file_extension(filename: str) -> str:
    name = (filename or "").strip().lower()
    if name.endswith(".tar.gz"):
        return ".gz"
    return Path(name).suffix


def is_allowed_package(filename: str) -> bool:
    return file_extension(filename) in ALLOWED_EXTENSIONS


def parse_appstore_track_id(url: str) -> str | None:
    text = (url or "").strip()
    if not text:
        return None
    match = APPSTORE_ID_RE.search(text)
    if not match:
        return None
    return next((g for g in match.groups() if g), None)


def is_appstore_url(url: str) -> bool:
    text = (url or "").strip().lower()
    if not text:
        return False
    if "apps.apple.com" not in text and "itunes.apple.com" not in text:
        return False
    return parse_appstore_track_id(text) is not None


def split_features(text: str) -> list[str]:
    lines = []
    for raw in (text or "").splitlines():
        piece = raw.strip()
        if not piece:
            continue
        piece = re.sub(r"^[\-–—*•⦁◦]+\s*", "", piece)
        if piece:
            lines.append(piece)
    return lines


def feature_emoji_key(text: str) -> str:
    for pattern, key in _FEATURE_RULES:
        if pattern.search(text or ""):
            return key
    return "sparkle"


def caption_visible_len(html_text: str) -> int:
    """Độ dài UTF-16 của chữ hiện ra, không tính thẻ HTML (giới hạn caption Telegram)."""
    text = re.sub(r"<[^>]+>", "", html_text or "")
    return len(html.unescape(text).encode("utf-16-le")) // 2


def _header_lines(
    title: str,
    version: str,
    bundle_id: str,
    store_url: str,
    *,
    include_bundle: bool,
) -> list[str]:
    lines = [f"<b>{title}</b>"]
    if version:
        lines.append(f"Phiên bản · <code>{html.escape(version)}</code>")
    if include_bundle and bundle_id:
        lines.append(f"Bundle · <code>{html.escape(bundle_id)}</code>")
    if store_url:
        safe_href = html.escape(store_url, quote=True)
        lines.append(f'<a href="{safe_href}">App Store</a>')
    return lines


def build_channel_caption(
    *,
    name: str,
    version: str = "",
    seller: str = "",
    bundle_id: str = "",
    store_url: str = "",
    features: list[str] | None = None,
    filename: str = "",
    emojis: dict | None = None,
    max_len: int = 1024,
) -> tuple[str, str | None]:
    """Dựng caption HTML không emoji. Trả về (caption, phần tràn nếu quá max_len chữ hiện ra).

    Tham số emojis, filename và seller giữ chữ ký cũ nhưng bị bỏ qua. Hiện
    Bundle ID thay cho người bán; chức năng bọc trong <blockquote expandable> (Telegram ẩn bớt khi dài).
    Mọi chữ người dùng (tên, version, bundle, feature) đều html.escape
    (& → &amp;) để Telegram parse HTML / blockquote không lỗi.
    """
    _ = emojis, filename, seller
    title = html.escape((name or "").strip() or "Ứng dụng")
    feature_lines = [
        f"• {html.escape(item, quote=False)}"
        for item in (features or [])
        if (item or "").strip()
    ]

    def compose(include_bundle: bool, feats: list[str]) -> str:
        lines = _header_lines(
            title, version, bundle_id, store_url, include_bundle=include_bundle,
        )
        if feats:
            quote = ["<b>Chức năng</b>", *feats]
            lines.append("")
            lines.append(BLOCKQUOTE_FEATURES_OPEN + "\n".join(quote) + "</blockquote>")
        return "\n".join(lines)

    for include_bundle in (True, False):
        caption = compose(include_bundle, feature_lines)
        if caption_visible_len(caption) <= max_len:
            return caption, None

    kept: list[str] = []
    overflow_rows: list[str] = []
    for row in feature_lines:
        trial = compose(False, kept + [row])
        if caption_visible_len(trial) > max_len:
            overflow_rows = feature_lines[len(kept):]
            break
        kept.append(row)
    caption = compose(False, kept)
    overflow = "\n".join(overflow_rows) if overflow_rows else None
    return caption, overflow



def build_delivery_captions(
    *,
    name: str = "",
    version: str = "",
    bundle_id: str = "",
    store_url: str = "",
    features: list[str] | None = None,
    caption_max: int = 1024,
    text_max: int = 4096,
) -> tuple[str, str | None]:
    """Caption gửi kèm file (≤ caption_max) và follow-up text nếu bị cắt (≤ text_max).

    Follow-up là bản đầy đủ thông tin + chức năng để không mất nội dung.
    Bản ghi cũ thiếu meta → chỉ trả title đậm, không follow-up.
    """
    feats = [f for f in (features or []) if (f or "").strip()]
    has_meta = bool((version or "").strip() or (bundle_id or "").strip() or (store_url or "").strip() or feats)
    if not has_meta:
        title = html.escape((name or "").strip() or "File")
        return f"<b>{title}</b>", None

    file_caption, overflow = build_channel_caption(
        name=name or "Ứng dụng",
        version=version or "",
        bundle_id=bundle_id or "",
        store_url=store_url or "",
        features=feats,
        max_len=caption_max,
    )
    if not overflow:
        return file_caption, None
    full, _ = build_channel_caption(
        name=name or "Ứng dụng",
        version=version or "",
        bundle_id=bundle_id or "",
        store_url=store_url or "",
        features=feats,
        max_len=text_max,
    )
    return file_caption, full


def normalize_stored_features(raw) -> list[str]:
    """Đọc features từ Mongo (list hoặc chuỗi nhiều dòng)."""
    if raw is None:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            piece = str(item or "").strip()
            if piece:
                out.append(piece)
        return out
    return split_features(str(raw))


def _load_title_font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rounded_icon(icon: Image.Image, radius: int) -> Image.Image:
    icon = icon.convert("RGBA")
    mask = Image.new("L", icon.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, icon.size[0], icon.size[1]), radius=radius, fill=255)
    out = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    out.paste(icon, (0, 0))
    out.putalpha(mask)
    return out


def render_appstore_poster(icon_data: bytes, title: str = "", size: int = 1080) -> bytes:
    """Render poster vuông: nền icon làm mờ + icon bo góc ở giữa."""
    src = Image.open(io.BytesIO(icon_data)).convert("RGBA")
    bg = src.resize((size, size), getattr(Image, "LANCZOS", Image.BICUBIC)).convert("RGB")
    bg = bg.filter(ImageFilter.GaussianBlur(36))
    bg = ImageEnhance.Brightness(bg).enhance(0.42)
    bg = ImageEnhance.Color(bg).enhance(1.05)

    icon_size = int(size * 0.58)
    icon = src.resize((icon_size, icon_size), getattr(Image, "LANCZOS", Image.BICUBIC))
    icon = _rounded_icon(icon, radius=max(36, icon_size // 6))

    canvas = bg.convert("RGBA")
    x = (size - icon_size) // 2
    y = int(size * 0.16) if (title or "").strip() else (size - icon_size) // 2
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    pad = 18
    sd.rounded_rectangle(
        (x - pad, y - pad, x + icon_size + pad, y + icon_size + pad),
        radius=max(48, icon_size // 6) + pad,
        fill=(0, 0, 0, 90),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.paste(icon, (x, y), icon)

    label = (title or "").strip()
    if label:
        if len(label) > 28:
            label = label[:27].rstrip() + "…"
        draw = ImageDraw.Draw(canvas)
        font = _load_title_font(max(36, size // 18))
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (size - tw) // 2
        ty = min(size - th - 56, y + icon_size + 48)
        draw.text((tx + 2, ty + 2), label, font=font, fill=(0, 0, 0, 140))
        draw.text((tx, ty), label, font=font, fill=(255, 255, 255, 235))

    rgb = canvas.convert("RGB")
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


async def lookup_appstore(url: str) -> dict | None:
    """Tra iTunes theo link App Store. Trả None nếu không parse/lookup được."""
    track_id = parse_appstore_track_id(url)
    if not track_id:
        return None
    from dorasuper.helper import rename_utils as ru

    if not getattr(ru, "aiohttp", None):
        return None
    app = None
    try:
        async with ru.aiohttp.ClientSession() as session:
            app = await ru._lookup_by_track_id(session, track_id)
            if not app:
                for country in ("vn", "us", "gb"):
                    lookup = f"https://itunes.apple.com/lookup?id={track_id}&country={country}"
                    try:
                        async with session.get(
                            lookup,
                            timeout=ru.aiohttp.ClientTimeout(total=15),
                            headers=ru.ITUNES_HEADERS,
                        ) as resp:
                            if resp.status != 200:
                                continue
                            data = await resp.json(content_type=None)
                    except Exception:
                        continue
                    if data.get("resultCount", 0):
                        app = data["results"][0]
                        break
    except Exception:
        return None
    if not app:
        return None
    assets = ru._assets_from_app(app)
    assets.update(
        {
            "seller_name": app.get("sellerName") or "",
            "track_view_url": app.get("trackViewUrl") or "",
            "bundle_id": app.get("bundleId") or "",
            "track_id": str(app.get("trackId") or track_id),
        }
    )
    art_url = ru._best_art_url(assets) or assets.get("icon_512") or assets.get("icon_100")
    icon_bytes = await ru._download_artwork_bytes(art_url) if art_url else None
    assets["icon_bytes"] = icon_bytes
    return assets
