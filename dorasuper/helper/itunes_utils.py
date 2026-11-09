"""iTunes / App Store helpers shared by /up (tách từ rename_utils)."""
from __future__ import annotations

import asyncio
import logging
import re

try:
    import aiohttp
except ImportError:  # môi trường test có thể thiếu
    aiohttp = None

try:
    import requests as _requests
except ImportError:
    _requests = None

_log = logging.getLogger("DoraSuper.itunes_utils")

ITUNES_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
ARTWORK_HEADERS = {**ITUNES_HEADERS, "Referer": "https://itunes.apple.com/"}


def artwork_url_larger(url: str) -> str:
    """Đổi URL icon 60/100 thành 512x512 khi được."""
    if not url:
        return url
    if "100x100" in url or "60x60" in url:
        return re.sub(r"\d+x\d+", "512x512", url, count=1)
    return url


def _assets_from_app(app: dict) -> dict:
    return {
        "track_name": app.get("trackName"),
        "icon_512": app.get("artworkUrl512"),
        "icon_100": app.get("artworkUrl100"),
        "icon_60": app.get("artworkUrl60"),
        "screenshot_iphone": app.get("screenshotUrls", []),
        "screenshot_ipad": app.get("ipadScreenshotUrls", []),
        "version": app.get("version"),
    }


def _best_art_url(assets: dict | None) -> str:
    if not assets:
        return ""
    return assets.get("icon_512") or assets.get("icon_100") or assets.get("icon_60") or ""


def _download_artwork_requests(icon_url: str):
    if not _requests or not icon_url:
        return None
    try:
        return _requests.get(icon_url, timeout=10, headers=ITUNES_HEADERS).content
    except Exception:
        return None


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


async def _download_artwork_bytes(art_url: str):
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
    loop = asyncio.get_event_loop()
    for url in urls_to_try:
        raw = await loop.run_in_executor(None, _download_artwork_requests, url)
        if raw:
            return raw
    return None
