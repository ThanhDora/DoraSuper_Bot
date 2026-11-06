"""Yeta media API client (image/video). Không import app để test được."""
import asyncio
import base64
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
VIDEO_DAILY_LIMIT = 2
NO_IMAGE_MODEL_MSG = (
    "API hiện tại chỉ có model tạo video (Seedance), chưa có model tạo ảnh. "
    "Anh/chị dùng lệnh /taovideo nội dung cần tạo để tạo video nhé."
)


class YetaError(Exception):
    def __init__(self, message: str, code: str = "", status: int = 0):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status

    @property
    def model_not_found(self) -> bool:
        t = f"{self.code} {self.message}".lower()
        return "model_not_found" in t or "no available channel" in t


def vn_date_str(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(VN_TZ).strftime("%Y-%m-%d")


def remaining_videos(used: int, limit: int = VIDEO_DAILY_LIMIT) -> int:
    return max(0, limit - int(used or 0))


def is_private_chat(chat_type) -> bool:
    v = getattr(chat_type, "value", chat_type)
    return str(v).lower() in ("private", "chattype.private")


def clamp_seconds(s: int) -> int:
    return max(4, min(15, int(s)))


def sanitize_error(msg, token: str = "") -> str:
    msg = str(msg or "Lỗi không xác định")
    if token:
        msg = msg.replace(token, "***")
    msg = re.sub(r"(?i)bearer\s+\S+", "Bearer ***", msg)
    msg = re.sub(r"sk-[A-Za-z0-9]{8,}", "***", msg)
    if len(msg) > 300:
        msg = msg[:300] + "…"
    return html.escape(msg)


def parse_error(status: int, data) -> YetaError:
    code, message = "", ""
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("type") or "")
            message = str(err.get("message") or "")
        elif isinstance(err, str):
            message = err
        code = code or str(data.get("code") or "")
        message = message or str(data.get("message") or data.get("detail") or "")
    elif isinstance(data, str):
        message = data[:300]
    return YetaError(message or f"HTTP {status}", code, status)


def parse_image_response(data) -> tuple[str, bytes | str]:
    """Trả về ("bytes", b) hoặc ("url", url)."""
    items = data.get("data") if isinstance(data, dict) else None
    if isinstance(items, list) and items:
        it = items[0] or {}
        if it.get("b64_json"):
            b = it["b64_json"]
            if b.startswith("data:"):
                b = b.split(",", 1)[1]
            return "bytes", base64.b64decode(b)
        if it.get("url"):
            return "url", it["url"]
    if isinstance(data, dict) and data.get("url"):
        return "url", data["url"]
    raise YetaError("Không nhận được ảnh từ máy chủ.")


def parse_video_job(data) -> dict:
    if not isinstance(data, dict):
        raise YetaError("Phản hồi tạo video không hợp lệ.")
    d = data.get("data") if isinstance(data.get("data"), dict) else data
    jid = d.get("id") or d.get("task_id")
    status = str(d.get("status") or "").lower()
    url = d.get("url") or d.get("video_url")
    if not url and isinstance(d.get("content"), dict):
        url = d["content"].get("video_url")
    err = d.get("error")
    if isinstance(err, dict):
        err = err.get("message")
    return {"id": jid, "status": status, "url": url, "error": err or d.get("fail_reason")}


class YetaClient:
    def __init__(self, base_url: str, token: str, timeout: float = 120):
        self.base = (base_url or "https://platform.yeta.ai").rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

    async def _request(self, method, path, json=None):
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as c:
            r = await c.request(method, self.base + path, headers=self._headers(), json=json)
        try:
            data = r.json()
        except Exception:
            data = r.text
        if r.status_code >= 400 or (isinstance(data, dict) and data.get("error")
                                    and not data.get("data") and not data.get("id")):
            raise parse_error(r.status_code, data)
        return data

    async def generate_image(self, model: str, prompt: str):
        if not model:
            raise YetaError("model_not_found", "model_not_found")
        data = await self._request("POST", "/v1/images/generations", {
            "model": model, "prompt": prompt, "response_format": "b64_json", "watermark": False,
        })
        return parse_image_response(data)

    async def submit_video(self, model, prompt, seconds=5, resolution="720p") -> dict:
        data = await self._request("POST", "/v1/videos", {
            "model": model, "prompt": prompt,
            "seconds": clamp_seconds(seconds), "resolution": resolution,
        })
        job = parse_video_job(data)
        if not job["id"]:
            raise YetaError(job.get("error") or "Máy chủ không trả về mã tác vụ video.")
        return job

    async def wait_video(self, job_id, timeout=360, interval=5) -> dict:
        loop = asyncio.get_event_loop()
        end = loop.time() + timeout
        fails = 0
        while loop.time() < end:
            await asyncio.sleep(interval)
            try:
                job = parse_video_job(await self._request("GET", f"/v1/videos/{job_id}"))
                fails = 0
            except YetaError as e:
                if e.status >= 500 and fails < 6:
                    fails += 1
                    continue
                raise
            except httpx.HTTPError:
                fails += 1
                if fails > 6:
                    raise
                continue
            if job["status"] in ("completed", "succeeded", "success"):
                return job
            if job["status"] in ("failed", "error", "cancelled"):
                raise YetaError(job.get("error") or "Tạo video thất bại.")
        raise asyncio.TimeoutError

    async def download_video(self, job_id) -> bytes:
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
            r = await c.get(f"{self.base}/v1/videos/{job_id}/content", headers=self._headers())
            r.raise_for_status()
            return r.content
