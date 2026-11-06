"""Hàm thuần cho tính năng đổi tên file (không phụ thuộc pyrogram, dễ test)."""
import json
import os
import re
import asyncio

MAX_RENAME_SIZE = 2000 * 1024 * 1024  # giới hạn upload của bot (~2GB)


def add_prefix_suffix(name: str, prefix: str = None, suffix: str = None) -> str:
    m = re.search(r"(?P<filename>.*?)(\.\w+)?$", name)
    if not m:
        return name
    base, ext = m.group("filename"), m.group(2) or ""
    p = f"{prefix} " if prefix else ""
    s = f" {suffix}" if suffix else ""
    return f"{p}{base}{s}{ext}"


def ensure_extension(new_name: str, old_name: str) -> str:
    new_name = new_name.strip()
    if "." in new_name:
        return new_name
    ext = old_name.rsplit(".", 1)[-1] if old_name and "." in old_name else "mkv"
    return f"{new_name}.{ext}"


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip()
    return name[:200] or "file"


def parse_metadata(text: str):
    """Trả về dict: author, title, video_title, audio_title, subtitle_title."""
    out = dict.fromkeys(("author", "title", "video_title", "audio_title", "subtitle_title"))
    keys = {
        "change-video-title": "video_title",
        "change-audio-title": "audio_title",
        "change-subtitle-title": "subtitle_title",
        "change-author": "author",
        "change-title": "title",
    }
    for flag in (f.strip() for f in (text or "").split("--")):
        for k, field in keys.items():
            if flag.startswith(k + " ") or flag == k:
                out[field] = flag[len(k):].strip() or None
                break
    return out


def format_caption(template: str, filename: str, filesize: str, duration: str, gamename: str = "") -> str:
    if not template:
        return f"<b>{filename}</b>"
    for k, v in {
        "{filename}": filename,
        "{filesize}": filesize,
        "{duration}": duration,
        "{gamename}": gamename or "",
    }.items():
        template = template.replace(k, str(v))
    return template


def convert_duration(seconds: int) -> str:
    seconds = int(seconds or 0)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_ffmpeg_cmd(input_file, output_file, meta: dict, streams: list):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", input_file, "-map", "0", "-c", "copy"]
    if meta.get("title"):
        cmd += ["-metadata", f"title={meta['title']}"]
    if meta.get("author"):
        cmd += ["-metadata", f"author={meta['author']}", "-metadata", f"artist={meta['author']}"]
    per = {"video": "video_title", "audio": "audio_title", "subtitle": "subtitle_title"}
    for st in streams:
        field = per.get(st.get("codec_type"))
        if field and meta.get(field):
            cmd += [f"-metadata:s:{st['index']}", f"title={meta[field]}"]
    cmd.append(output_file)
    return cmd


async def _run(*cmd):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode, out, err


async def probe(path: str) -> dict:
    try:
        rc, out, _ = await _run("ffprobe", "-v", "error", "-show_streams", "-show_format", "-print_format", "json", path)
        return json.loads(out) if rc == 0 else {}
    except Exception:
        return {}


async def change_metadata(input_file: str, output_file: str, metadata_text: str) -> bool:
    info = await probe(input_file)
    if not info.get("streams"):
        return False
    cmd = build_ffmpeg_cmd(input_file, output_file, parse_metadata(metadata_text), info["streams"])
    try:
        rc, _, _ = await _run(*cmd)
    except Exception:
        return False
    return rc == 0 and os.path.exists(output_file) and os.path.getsize(output_file) > 0


# ---------- Apple iTunes artwork (port từ misyou_iBot, không BotLog/admin) ----------
import logging
import plistlib
import tempfile
import zipfile
import tarfile
from io import BytesIO
from pathlib import Path

try:
    import aiohttp
except ImportError:  # môi trường test có thể thiếu
    aiohttp = None

try:
    import requests as _requests
except ImportError:
    _requests = None

from PIL import Image

_log = logging.getLogger("DoraSuper.rename_utils")
ITUNES_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
ARTWORK_HEADERS = {**ITUNES_HEADERS, "Referer": "https://itunes.apple.com/"}
LOOKUP_COUNTRIES = ("us", "vn", "gb", "kr", "jp", "sg", "au", "ca")


def artwork_url_larger(url: str) -> str:
    """Đổi URL icon 60/100 thành 512x512 khi được."""
    if not url:
        return url
    if "100x100" in url or "60x60" in url:
        return re.sub(r"\d+x\d+", "512x512", url, count=1)
    return url


# alias tương thích tên nguồn
_artwork_url_larger = artwork_url_larger


def sanitize_filename_for_app(name: str) -> str:
    s = re.sub(r'[/\\:*?"<>|]', "", (name or "").strip())
    return (s[:200] or "App").strip()


def prepare_thumb_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        return bg
    return img.convert("RGB")


def create_itunes_artwork(icon_data: bytes, size: int = 1024) -> bytes:
    img = Image.open(BytesIO(icon_data)).convert("RGBA")
    img = img.resize((size, size), getattr(Image, "LANCZOS", Image.BICUBIC))
    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _bundle_id_from_plist(plist):
    try:
        bundle_id = plist.get("CFBundleIdentifier")
        if bundle_id and isinstance(bundle_id, str):
            app_name = plist.get("CFBundleDisplayName") or plist.get("CFBundleName") or None
            version = plist.get("CFBundleShortVersionString") or plist.get("CFBundleVersion") or None
            return bundle_id, app_name, version
        filter_dict = plist.get("Filter")
        if isinstance(filter_dict, dict):
            bundles = filter_dict.get("Bundles")
            if isinstance(bundles, list):
                for b in bundles:
                    if b and isinstance(b, str):
                        return b, None, None
                    if b:
                        return str(b), None, None
            if isinstance(bundles, dict):
                for b in bundles:
                    if b:
                        return (b, None, None) if isinstance(b, str) else (str(b), None, None)
    except Exception:
        pass
    return None, None, None


def _scan_plists_for_bundle_id(root_dir):
    for dirpath, _, filenames in os.walk(root_dir):
        for name in filenames:
            if not name.lower().endswith(".plist"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as fp:
                    plist = plistlib.load(fp)
                bundle_id, app_name, version = _bundle_id_from_plist(plist)
                if bundle_id:
                    return bundle_id, app_name, version
            except Exception:
                continue
    return None, None, None


def extract_bundle_info_from_ipa(ipa_path):
    if not ipa_path or not os.path.lexists(ipa_path):
        return None, None, None
    try:
        with zipfile.ZipFile(ipa_path, "r") as z:
            for name in z.namelist():
                if name.startswith("Payload/") and name.endswith(".app/Info.plist"):
                    with z.open(name) as plist_file:
                        plist = plistlib.load(plist_file)
                        bundle_id = plist.get("CFBundleIdentifier")
                        if bundle_id and isinstance(bundle_id, str):
                            app_name = (
                                plist.get("CFBundleDisplayName")
                                or plist.get("CFBundleName")
                                or None
                            )
                            version = (
                                plist.get("CFBundleShortVersionString")
                                or plist.get("CFBundleVersion")
                                or None
                            )
                            return bundle_id, app_name, version
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(ipa_path, "r") as z:
                z.extractall(tmp)
            return _scan_plists_for_bundle_id(tmp)
    except Exception:
        return None, None, None


def _extract_data_tar_io_from_deb(deb_path):
    with open(deb_path, "rb") as f:
        data = f.read()
    if not data.startswith(b"!<arch>\n"):
        return None
    offset = 8
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) < 60:
            break
        name = header[:16].decode("ascii", errors="ignore").strip()
        try:
            size = int(header[48:58].decode("ascii", errors="ignore").strip())
        except ValueError:
            break
        offset += 60
        if offset + size > len(data):
            break
        file_data = data[offset:offset + size]
        offset += size
        if offset % 2:
            offset += 1
        if name.startswith("data.tar"):
            return BytesIO(file_data)
    return None


def extract_bundle_info_from_deb(deb_path):
    if not deb_path or not os.path.lexists(deb_path):
        return None, None, None
    try:
        data_tar_io = _extract_data_tar_io_from_deb(deb_path)
        if not data_tar_io:
            return None, None, None
        with tempfile.TemporaryDirectory() as tmp:
            try:
                with tarfile.open(fileobj=data_tar_io, mode="r:*") as tar:
                    tar.extractall(tmp)
            except Exception:
                return None, None, None
            dylib_dir = os.path.join(tmp, "Library", "MobileSubstrate", "DynamicLibraries")
            if os.path.isdir(dylib_dir):
                for fname in os.listdir(dylib_dir):
                    if fname.endswith(".plist"):
                        try:
                            with open(os.path.join(dylib_dir, fname), "rb") as fp:
                                plist = plistlib.load(fp)
                            bundles = plist.get("Filter", {}).get("Bundles", [])
                            if isinstance(bundles, list) and bundles:
                                b = bundles[0]
                                return (b, None, None) if isinstance(b, str) else (str(b), None, None)
                        except Exception:
                            continue
            return _scan_plists_for_bundle_id(tmp)
    except Exception:
        return None, None, None


def get_bundle_id_from_file(file_path, extension_hint=None):
    if not file_path or not os.path.lexists(file_path):
        return None, None, None
    low = (extension_hint or file_path).lower()
    if low.endswith(".ipa"):
        return extract_bundle_info_from_ipa(file_path)
    if low.endswith(".deb"):
        return extract_bundle_info_from_deb(file_path)
    return None, None, None


def inject_itunes_artwork_into_ipa(ipa_path, artwork_bytes, out_dir=None):
    """Chèn file iTunesArtwork vào IPA (copy zip, không giải nén hết)."""
    ipa_path = Path(ipa_path).resolve()
    if not ipa_path.exists():
        return None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        fd, out_ipa = tempfile.mkstemp(suffix=".ipa", prefix="ipa_art_", dir=out_dir)
    else:
        fd, out_ipa = tempfile.mkstemp(suffix=".ipa", prefix="ipa_art_")
    os.close(fd)
    try:
        with zipfile.ZipFile(ipa_path, "r") as zin, zipfile.ZipFile(
            out_ipa, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                if item.filename == "iTunesArtwork":
                    continue
                zout.writestr(item, zin.read(item.filename))
            zout.writestr("iTunesArtwork", artwork_bytes)
        return out_ipa
    except Exception as e:
        _log.warning("inject_itunes_artwork_into_ipa: %s", e)
        try:
            os.unlink(out_ipa)
        except Exception:
            pass
        return None


def _itunes_lookup_requests(bundle_id):
    if not _requests:
        return None
    for url in (
        f"https://itunes.apple.com/lookup?bundleId={bundle_id}",
        f"https://itunes.apple.com/lookup?bundleId={bundle_id}&country=us",
    ):
        try:
            data = _requests.get(url, timeout=15, headers=ITUNES_HEADERS).json()
            if data.get("resultCount", 0) == 0:
                continue
            app = data["results"][0]
            icon = app.get("artworkUrl512") or app.get("artworkUrl100")
            return {
                "icon_512": app.get("artworkUrl512"),
                "icon_100": app.get("artworkUrl100"),
                "icon": icon,
                "track_name": app.get("trackName"),
                "version": app.get("version"),
            }
        except Exception:
            continue
    return None


def _download_artwork_requests(icon_url):
    if not _requests or not icon_url:
        return None
    try:
        return _requests.get(icon_url, timeout=10, headers=ITUNES_HEADERS).content
    except Exception:
        return None


def _fetch_icon_bytes_requests_sync(bundle_id):
    info = _itunes_lookup_requests(bundle_id)
    if not info or not info.get("icon"):
        return None
    return _download_artwork_requests(info["icon"])


def _assets_from_app(app):
    return {
        "track_name": app.get("trackName"),
        "icon_512": app.get("artworkUrl512"),
        "icon_100": app.get("artworkUrl100"),
        "icon_60": app.get("artworkUrl60"),
        "screenshot_iphone": app.get("screenshotUrls", []),
        "screenshot_ipad": app.get("ipadScreenshotUrls", []),
        "version": app.get("version"),
    }


async def _lookup_one(bundle_id, country=None):
    if not aiohttp:
        return None
    url = f"https://itunes.apple.com/lookup?bundleId={bundle_id}"
    if country:
        url += f"&country={country}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15), headers=ITUNES_HEADERS
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
        if data.get("resultCount", 0) == 0:
            return None
        return data["results"][0]
    except Exception:
        return None


async def get_itunes_assets(bundle_id):
    app = await _lookup_one(bundle_id)
    if not app:
        for country in LOOKUP_COUNTRIES:
            app = await _lookup_one(bundle_id, country)
            if app:
                break
    if not app:
        return None
    return _assets_from_app(app)


def _search_terms_for_bundle(bundle_id):
    b = (bundle_id or "").strip()
    if not b:
        return []
    parts = [p for p in b.split(".") if p]
    terms = [b]
    if len(parts) >= 2:
        terms.append(parts[-1])
        terms.append(parts[-2])
        terms.append(f"{parts[-2]} {parts[-1]}")
        slug = parts[-1].replace("_", "-")
        if slug != parts[-1]:
            terms.append(slug)
    elif len(parts) == 1:
        terms.append(parts[0])
    return list(dict.fromkeys(terms))


async def _search_itunes_one(session, term, country):
    url = f"https://itunes.apple.com/search?term={re.escape(term)}&entity=software&limit=25&country={country}"
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=15), headers=ITUNES_HEADERS
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
        return data.get("results") or []
    except Exception:
        return []


async def _lookup_by_track_id(session, track_id):
    url = f"https://itunes.apple.com/lookup?id={track_id}"
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=15), headers=ITUNES_HEADERS
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
        if data.get("resultCount", 0) == 0:
            return None
        return data["results"][0]
    except Exception:
        return None


def _extract_app_ids_from_appstore_html(html):
    return list(dict.fromkeys(re.findall(r"/app/[^/]+/id(\d+)", html or "")))


async def get_itunes_assets_via_search(bundle_id):
    if not aiohttp:
        return None
    bundle_lower = (bundle_id or "").strip().lower()
    terms = _search_terms_for_bundle(bundle_id)
    countries = ("us", "vn", "gb", "kr", "jp")
    try:
        async with aiohttp.ClientSession() as session:
            for country in countries:
                for term in terms:
                    results = await _search_itunes_one(session, term, country)
                    for app in results:
                        if (app.get("bundleId") or "").strip().lower() == bundle_lower:
                            return _assets_from_app(app)
    except Exception:
        pass
    return None


async def get_itunes_assets_via_appstore_web(bundle_id):
    if not aiohttp:
        return None
    bundle_lower = (bundle_id or "").strip().lower()
    terms = _search_terms_for_bundle(bundle_id)
    try:
        async with aiohttp.ClientSession() as session:
            for term in terms[:6]:
                url = f"https://apps.apple.com/us/search?term={re.escape(term)}"
                try:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=20), headers=ITUNES_HEADERS
                    ) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()
                except Exception:
                    continue
                for app_id in _extract_app_ids_from_appstore_html(html)[:15]:
                    app = await _lookup_by_track_id(session, app_id)
                    if app and (app.get("bundleId") or "").strip().lower() == bundle_lower:
                        return _assets_from_app(app)
    except Exception:
        pass
    return None


async def _download_artwork_bytes(art_url):
    if not art_url:
        return None
    urls_to_try = [art_url]
    larger = artwork_url_larger(art_url)
    if larger and larger != art_url:
        urls_to_try.append(larger)
    if aiohttp:
        for headers in (ARTWORK_HEADERS, ITUNES_HEADERS):
            try:
                async with aiohttp.ClientSession() as session:
                    for url in urls_to_try:
                        try:
                            async with session.get(
                                url, timeout=aiohttp.ClientTimeout(total=25), headers=headers
                            ) as resp:
                                if resp.status == 200:
                                    return await resp.read()
                        except Exception:
                            continue
            except Exception:
                pass
    # fallback sync
    loop = asyncio.get_event_loop()
    for url in urls_to_try:
        raw = await loop.run_in_executor(None, _download_artwork_requests, url)
        if raw:
            return raw
    return None


def _best_art_url(assets):
    if not assets:
        return ""
    return assets.get("icon_512") or assets.get("icon_100") or assets.get("icon_60") or ""


async def fetch_icon_from_bundle(bundle_id):
    bundle_id = (bundle_id or "").strip()
    if not bundle_id:
        return None
    for getter in (get_itunes_assets, get_itunes_assets_via_search, get_itunes_assets_via_appstore_web):
        try:
            assets = await getter(bundle_id)
            art = _best_art_url(assets)
            if art:
                raw = await _download_artwork_bytes(art)
                if raw:
                    return raw
        except Exception:
            pass
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _fetch_icon_bytes_requests_sync, bundle_id)
    except Exception:
        return None


async def fetch_itunes_track_name(bundle_id):
    bundle_id = (bundle_id or "").strip()
    if not bundle_id:
        return None
    for getter in (get_itunes_assets, get_itunes_assets_via_search, get_itunes_assets_via_appstore_web):
        try:
            assets = await getter(bundle_id)
            if assets:
                name = (assets.get("track_name") or "").strip()
                if name:
                    return name
        except Exception:
            pass
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _itunes_lookup_requests, bundle_id)
        return (info or {}).get("track_name") or None
    except Exception:
        return None


async def fetch_itunes_version(bundle_id):
    bundle_id = (bundle_id or "").strip()
    if not bundle_id:
        return None
    for getter in (get_itunes_assets, get_itunes_assets_via_search, get_itunes_assets_via_appstore_web):
        try:
            assets = await getter(bundle_id)
            if assets:
                v = assets.get("version")
                if v is not None and str(v).strip():
                    return str(v).strip()
        except Exception:
            pass
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _itunes_lookup_requests, bundle_id)
        return (info or {}).get("version") or None
    except Exception:
        return None


async def fetch_itunes_artwork(bundle_id, out_dir=None):
    """Tải artwork iTunes → (path, error_msg)."""
    bundle_id = (bundle_id or "").strip()
    if not bundle_id:
        return None, "Bundle ID trống."
    raw = await fetch_icon_from_bundle(bundle_id)
    if not raw:
        return None, "Không tìm thấy trên iTunes."
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        fd, path = tempfile.mkstemp(suffix=".png", prefix="itunes_", dir=out_dir)
    else:
        fd, path = tempfile.mkstemp(suffix=".png", prefix="itunes_")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(raw)
        return path, None
    except Exception as e:
        try:
            os.unlink(path)
        except Exception:
            pass
        return None, str(e)


async def fetch_itunes_artwork_and_inject_ipa(bundle_id, ipa_path, out_dir=None):
    """Render artwork 1024, chèn vào IPA, trả (modified_ipa, thumb_path, error)."""
    icon_bytes = await fetch_icon_from_bundle(bundle_id)
    if not icon_bytes:
        return None, None, "Không lấy được icon từ iTunes."
    artwork_bytes = create_itunes_artwork(icon_bytes, size=1024)
    modified_ipa = inject_itunes_artwork_into_ipa(ipa_path, artwork_bytes, out_dir=out_dir)
    if not modified_ipa:
        return None, None, "Không chèn được iTunesArtwork vào IPA."
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        fd, thumb_path = tempfile.mkstemp(suffix=".png", prefix="itunes_thumb_", dir=out_dir)
    else:
        fd, thumb_path = tempfile.mkstemp(suffix=".png", prefix="itunes_thumb_")
    os.close(fd)
    try:
        with open(thumb_path, "wb") as f:
            f.write(artwork_bytes)
        return modified_ipa, thumb_path, None
    except Exception:
        try:
            os.unlink(thumb_path)
        except Exception:
            pass
        return modified_ipa, None, None
