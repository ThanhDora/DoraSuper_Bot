"""Grok Imagine video client (xAI). Không import app để test được."""
import asyncio
import html
import re

import httpx

XAI_BASE_URL = "https://api.x.ai"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
DURATION_MIN, DURATION_MAX = 1, 15


class GrokVideoError(Exception):
    def __init__(self, message: str, code: str = "", status: int = 0):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def clamp_duration(s: int) -> int:
    return max(DURATION_MIN, min(DURATION_MAX, int(s)))


def sanitize_error(msg, token: str = "") -> str:
    msg = str(msg or "Lỗi không xác định")
    if token:
        msg = msg.replace(token, "***")
    msg = re.sub(r"(?i)bearer\s+\S+", "Bearer ***", msg)
    msg = re.sub(r"(?i)xai-[A-Za-z0-9_-]{8,}", "***", msg)
    msg = re.sub(r"sk-[A-Za-z0-9]{8,}", "***", msg)
    if len(msg) > 300:
        msg = msg[:300] + "…"
    return html.escape(msg)


def parse_error(status: int, data) -> GrokVideoError:
    code, message = "", ""
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("type") or "")
            message = str(err.get("message") or err.get("detail") or "")
        elif isinstance(err, str):
            message = err
        code = code or str(data.get("code") or "")
        message = message or str(data.get("message") or data.get("detail") or "")
    elif isinstance(data, str):
        message = data[:300]
    return GrokVideoError(message or f"HTTP {status}", code, status)


def parse_submit(data) -> dict:
    if not isinstance(data, dict):
        raise GrokVideoError("Phản hồi tạo video không hợp lệ.")
    jid = data.get("request_id") or data.get("id")
    if not jid:
        raise GrokVideoError("Máy chủ không trả về mã tác vụ video.")
    return {"id": jid, "status": str(data.get("status") or "pending")}


def parse_status(data) -> dict:
    if not isinstance(data, dict):
        raise GrokVideoError("Phản hồi trạng thái video không hợp lệ.")
    status = str(data.get("status") or "").lower()
    url = ""
    video = data.get("video")
    if isinstance(video, dict):
        url = video.get("url") or ""
    url = url or data.get("url") or ""
    err = data.get("error")
    code, message = "", ""
    if isinstance(err, dict):
        code = str(err.get("code") or "")
        message = str(err.get("message") or "")
    elif isinstance(err, str):
        message = err
    return {"status": status, "url": url, "error": message, "code": code}


def friendly_grok_message(err: GrokVideoError) -> str:
    t = f"{err.code} {err.message} {err.status}".lower()
    if err.status in (401, 403) or "incorrect api key" in t or "invalid api key" in t or "permission_denied" in t:
        return "Key xAI chưa có quyền tạo video hoặc không hợp lệ. Anh/chị kiểm tra lại key trên xAI nhé."
    if err.status == 429 or "rate limit" in t or "too many" in t:
        return "Máy chủ đang giới hạn số lượt. Anh/chị thử lại sau ít phút nhé."
    if any(x in t for x in ("insufficient", "credit", "balance", "spending limit", "quota")):
        return "Tài khoản xAI không đủ hạn mức để tạo video. Anh/chị kiểm tra billing trên xAI rồi thử lại nhé."
    if any(x in t for x in ("moderation", "content policy", "safety", "blocked")):
        return "Nội dung này bị bộ lọc từ chối. Anh/chị thử mô tả khác nhé."
    if "invalid_argument" in t:
        return err.message or "Yêu cầu tạo video không hợp lệ. Anh/chị thử mô tả khác nhé."
    if "service_unavailable" in t or err.status >= 500:
        return "Máy chủ tạo video đang bận. Anh/chị thử lại sau ít phút nhé."
    return err.message


class GrokImagineClient:
    def __init__(self, token: str, timeout: float = 120, base_url: str = XAI_BASE_URL):
        self.token = token
        self.timeout = timeout
        self.base = (base_url or XAI_BASE_URL).rstrip("/")

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
        if r.status_code >= 400 or (isinstance(data, dict) and data.get("error") and not data.get("request_id")):
            raise parse_error(r.status_code, data)
        return data

    async def submit_video(self, model, prompt, duration=5, resolution="720p", aspect_ratio="16:9") -> dict:
        data = await self._request("POST", "/v1/videos/generations", {
            "model": model,
            "prompt": prompt,
            "duration": clamp_duration(duration),
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        })
        return parse_submit(data)

    async def wait_video(self, job_id, timeout=600, interval=5) -> dict:
        loop = asyncio.get_event_loop()
        end = loop.time() + timeout
        fails = 0
        while loop.time() < end:
            await asyncio.sleep(interval)
            try:
                job = parse_status(await self._request("GET", f"/v1/videos/{job_id}"))
                fails = 0
            except GrokVideoError as e:
                if e.status >= 500 and fails < 6:
                    fails += 1
                    continue
                raise
            except httpx.HTTPError:
                fails += 1
                if fails > 6:
                    raise
                continue
            if job["status"] in ("done", "completed", "succeeded", "success"):
                if not job.get("url"):
                    raise GrokVideoError("Video xong nhưng máy chủ không trả về đường dẫn.")
                return job
            if job["status"] in ("failed", "error", "expired", "cancelled"):
                raise GrokVideoError(job.get("error") or "Tạo video thất bại.", job.get("code") or "")
        raise asyncio.TimeoutError

    async def download_url(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {self.token}"})
            r.raise_for_status()
            return r.content
