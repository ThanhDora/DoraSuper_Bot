import os
import logging
from logging import getLogger
from asyncio import gather

from pyrogram.types import Message
from pySmartDL import SmartDL

from tiensiteo import app
from tiensiteo.core.decorator import new_task
from tiensiteo.helper.localization import use_chat_lang

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "ChụpWeb"
__HELP__ = """
<blockquote>/webss [URL] - Chụp ảnh màn hình một trang Web.</blockquote>
"""


@app.on_cmd("webss")
@new_task
@use_chat_lang()
async def take_ss(_, ctx: Message, strings):
    if len(ctx.command) == 1:
        return await ctx.reply_msg(strings("no_url"), del_in=6)
    url = (
        ctx.command[1]
        if ctx.command[1].startswith("http")
        else f"https://{ctx.command[1]}"
    )
    download_file_path = os.path.join("downloads/", f"webSS_{ctx.from_user.id}.png")
    msg = await ctx.reply_msg(strings("wait_str"))
    try:
        url = f"https://webss.yasirweb.eu.org/api/screenshot?resX=1280&resY=900&outFormat=jpg&waitTime=1000&isFullPage=false&dismissModals=false&url={url}"
        downloader = SmartDL(
            url, download_file_path, progress_bar=False, timeout=15, verify=False
        )
        downloader.start(blocking=True)
        await gather(
            *[
                # ctx.reply_document(download_file_path),
                ctx.reply_photo(download_file_path, caption=strings("str_credit")),
            ]
        )
        await msg.delete_msg()
        if os.path.exists(download_file_path):
            os.remove(download_file_path)
    except Exception as e:
        await msg.edit_msg(strings("ss_failed_str").format(err=str(e)))
