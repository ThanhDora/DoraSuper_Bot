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


def format_caption(template: str, filename: str, filesize: str, duration: str) -> str:
    if not template:
        return f"<b>{filename}</b>"
    for k, v in {"{filename}": filename, "{filesize}": filesize, "{duration}": duration}.items():
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
