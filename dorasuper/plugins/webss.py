import os
import asyncio
from logging import getLogger
from urllib.parse import quote

from pyrogram.enums import ParseMode
from pyrogram.types import Message
from pySmartDL import SmartDL

from dorasuper import app
from dorasuper.core.decorator import new_task
from dorasuper.emoji import E_ERROR, E_IMAGE, E_LOADING, E_TIP
from dorasuper.helper.localization import use_chat_lang

# Emoji cho locale webss (từ dorasuper/emoji.py)
WEBSS_EMOJI = {"E_TIP": E_TIP, "E_LOADING": E_LOADING, "E_IMAGE": E_IMAGE, "E_ERROR": E_ERROR}

LOGGER = getLogger("DoraSuper")

__MODULE__ = "ChụpWeb"
__HELP__ = """
<blockquote>/webss [URL] - Chụp ảnh màn hình một trang Web.</blockquote>
"""


def _download_webss(api_url: str, file_path: str) -> None:
    """Chạy trong executor để không block event loop."""
    downloader = SmartDL(
        api_url, file_path, progress_bar=False, timeout=15, verify=False
    )
    downloader.start(blocking=True)


@app.on_cmd("webss")
@new_task
@use_chat_lang()
async def take_ss(_, ctx: Message, strings):
    if len(ctx.command) == 1:
        return await ctx.reply_msg(
            strings("no_url").format(**WEBSS_EMOJI),
            del_in=6,
            parse_mode=ParseMode.HTML,
        )
    raw_url = (
        ctx.command[1]
        if ctx.command[1].startswith("http")
        else f"https://{ctx.command[1]}"
    )
    os.makedirs("downloads", exist_ok=True)
    download_file_path = os.path.join("downloads", f"webSS_{ctx.from_user.id}.png")
    msg = await ctx.reply_msg(
        strings("wait_str").format(**WEBSS_EMOJI),
        parse_mode=ParseMode.HTML,
    )
    try:
        api_url = (
            "https://webss.yasirweb.eu.org/api/screenshot?"
            "resX=1280&resY=900&outFormat=jpg&waitTime=1000&isFullPage=false&dismissModals=false&url="
            + quote(raw_url, safe="")
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _download_webss, api_url, download_file_path)
        if not os.path.exists(download_file_path):
            raise FileNotFoundError("API không trả về ảnh")
        await ctx.reply_photo(
            download_file_path,
            caption=strings("str_credit").format(**WEBSS_EMOJI),
            parse_mode=ParseMode.HTML,
        )
        await msg.delete_msg()
    except Exception as e:
        LOGGER.warning("webss failed: %s", e)
        await msg.edit_msg(
            strings("ss_failed_str").format(err=str(e), **WEBSS_EMOJI),
            parse_mode=ParseMode.HTML,
        )
    finally:
        if os.path.exists(download_file_path):
            try:
                os.remove(download_file_path)
            except OSError:
                pass
