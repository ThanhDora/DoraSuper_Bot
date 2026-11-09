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
        lines.append(f"iOS · <code>{html.escape(version)}</code>")
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
    Bundle ID thay cho người bán; chức năng bọc trong <blockquote>.
    """
    _ = emojis, filename, seller
    title = html.escape((name or "").strip() or "Ứng dụng")
    feature_lines = [f"• {html.escape(item)}" for item in (features or []) if (item or "").strip()]

    def compose(include_bundle: bool, feats: list[str]) -> str:
        lines = _header_lines(
            title, version, bundle_id, store_url, include_bundle=include_bundle,
        )
        if feats:
            quote = ["<b>Chức năng</b>", *feats]
            lines.append("")
            lines.append("<blockquote>" + "\n".join(quote) + "</blockquote>")
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
