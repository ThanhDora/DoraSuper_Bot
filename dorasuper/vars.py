import requests
import sys
from logging import getLogger
from os import environ
from pathlib import Path

import dotenv

LOGGER = getLogger("DoraSuper")

# Thư mục gốc dự án (để luôn dùng đúng assets/thumb.jpg dù chạy từ đâu)
ROOT_DIR = Path(__file__).resolve().parent.parent
THUMB_PATH = str(ROOT_DIR / "assets" / "thumb.jpg")

dotenv.load_dotenv("config.env", override=True)

if API_ID := environ.get("API_ID", ""):
    API_ID = int(API_ID)
else:
    LOGGER.error("API_ID variable is missing! Exiting now")
    sys.exit(1)
API_HASH = environ.get("API_HASH", "")
if not API_HASH:
    LOGGER.error("API_HASH variable is missing! Exiting now")
    sys.exit(1)
BOT_TOKEN = environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    LOGGER.error("BOT_TOKEN variable is missing! Exiting now")
    sys.exit(1)
DATABASE_URI = environ.get("DATABASE_URI", "")
if not DATABASE_URI:
    LOGGER.error("DATABASE_URI variable is missing! Exiting now")
    sys.exit(1)
if LOG_CHANNEL := environ.get("LOG_CHANNEL", ""):
    LOG_CHANNEL = int(LOG_CHANNEL)

else:
    LOGGER.error("LOG_CHANNEL variable is missing! Exiting now")
    sys.exit(1)
# Optional ENV
LOG_GROUP_ID = environ.get("LOG_GROUP_ID")
USER_SESSION = environ.get("USER_SESSION")
DATABASE_NAME = environ.get("DATABASE_NAME", "dorasuperDB")
TZ = environ.get("TZ", "Asia/Ho_Chi_Minh")
COMMAND_HANDLER = environ.get("COMMAND_HANDLER", "! /").split()
SUDO = list(
    {
        int(x)
        for x in environ.get(
            "SUDO",
            "",
        ).split()
    }
)
SUPPORT_CHAT = environ.get("SUPPORT_CHAT", "dabeecao")
AUTO_RESTART = environ.get("AUTO_RESTART", False)
# Emoji: True = gửi custom emoji (chỉ hiển thị premium nếu tài khoản chủ bot có Telegram Premium). False = dùng Unicode, hiển thị giống nhau cho mọi người.
USE_PREMIUM_EMOJI = environ.get("USE_PREMIUM_EMOJI", "true").strip().lower() in ("1", "true", "yes")

## Config For AUtoForwarder
# Forward From Chat ID
FORWARD_FROM_CHAT_ID = list(
    {
        int(x)
        for x in environ.get(
            "FORWARD_FROM_CHAT_ID",
            "",
        ).split()
    }
)
# Forward To Chat ID
FORWARD_TO_CHAT_ID = list(
    {int(x) for x in environ.get("FORWARD_TO_CHAT_ID", "").split()}
)
FORWARD_FILTERS = list(set(environ.get("FORWARD_FILTERS", "video document").split()))
BLOCK_FILES_WITHOUT_EXTENSIONS = bool(
    environ.get("BLOCK_FILES_WITHOUT_EXTENSIONS", True)
)
BLOCKED_EXTENSIONS = list(
    set(
        environ.get(
            "BLOCKED_EXTENSIONS",
            "html htm json txt php gif png ink torrent url nfo xml xhtml jpg",
        ).split()
    )
)
MINIMUM_FILE_SIZE = environ.get("MINIMUM_FILE_SIZE")
CURRENCY_API = environ.get("CURRENCY_API")
AI_API_KEY = environ.get("AI_API_KEY", "")
# AI: grok (xAI) hoặc gemini. Khi gemini cần thêm GEMINI_API_KEY
AI_PROVIDER = (environ.get("AI_PROVIDER", "grok") or "grok").strip().lower()
GEMINI_API_KEY = environ.get("GEMINI_API_KEY", "")
# Google Drive upload (getdirect): true = upload lên GDrive, false = dùng tmpfiles
USE_GDRIVE = environ.get("USE_GDRIVE", "").strip().lower() in ("1", "true", "yes")
GDRIVE_CREDENTIALS_PATH = environ.get("GDRIVE_CREDENTIALS_PATH", "")  # Đường dẫn file JSON service account
GDRIVE_FOLDER_ID = environ.get("GDRIVE_FOLDER_ID", "")  # ID thư mục Drive (để trống = upload vào My Drive gốc)
# Tmpfiles: tên field form (upload hoặc file). Đổi nếu server báo "No file uploaded"
TMPFILES_UPLOAD_FIELD = environ.get("TMPFILES_UPLOAD_FIELD", "file").strip() or "file"
# Cobalt API (TikTok video/ảnh): để trống = dùng yt-dlp + scrape. Ví dụ: https://api.cobalt.tools
COBALT_URL = (environ.get("COBALT_URL", "") or "").strip().rstrip("/")