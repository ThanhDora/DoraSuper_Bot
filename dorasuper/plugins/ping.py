import platform
import time
import logging
from logging import getLogger
from asyncio import Lock
from re import MULTILINE, findall
from subprocess import run as srun

from pyrogram import __version__ as pyrover
from pyrogram import enums, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from dorasuper import app, botStartTime, dorasuper_version
from dorasuper.emoji import E_CHECK, E_CLOCK, E_CROSS, E_MSG, E_ROCKET
from dorasuper.helper.human_read import get_readable_time
from dorasuper.helper.safe_reply import edit_safe, reply_safe
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")

PING_LOCK = Lock()


@app.on_message(filters.command(["ping"], COMMAND_HANDLER), group=-1)
async def ping(_, ctx: Message):
    currentTime = get_readable_time(time.time() - botStartTime)
    start_t = time.time()

    contact_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Liên hệ tác giả", url="t.me/dabeecao")]]
    )

    rm = await reply_safe(ctx, f"{E_ROCKET} Pong!!...", reply_markup=contact_button)
    if not rm:
        return

    end_t = time.time()
    time_taken_s = round(end_t - start_t, 3)

    body = (
        f"{E_ROCKET} <b>DoraSuper {dorasuper_version}</b> bởi @dabeecao dựa trên Pyrogram {pyrover}.\n\n"
        f"{E_CLOCK} <b>Thời gian phản hồi:</b> <code>{time_taken_s} ms</code>\n"
        f"{E_CLOCK} <b>Uptime:</b> <code>{currentTime}</code>\n\n"
        f"{E_MSG} Mọi thắc mắc và hợp tác vui lòng liên hệ tác giả. Ủng hộ: /donate"
    )
    await edit_safe(rm, body, reply_markup=contact_button)


@app.on_message(filters.command(["ping_dc"], COMMAND_HANDLER), group=-1)
async def ping_handler(_, ctx: Message):
    contact_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Liên hệ tác giả", url="t.me/dabeecao")]]
    )

    m = await reply_safe(ctx, f"{E_CLOCK} Pinging datacenters...", reply_markup=contact_button)
    if not m:
        return

    async with PING_LOCK:
        ips = {
            "dc1": "149.154.175.53",
            "dc2": "149.154.167.51",
            "dc3": "149.154.175.100",
            "dc4": "149.154.167.91",
            "dc5": "91.108.56.130",
        }
        text = "**Pings:**\n"

        for dc, ip in ips.items():
            try:
                shell = srun(
                    ["ping", "-c", "1", "-W", "2", ip],
                    text=True,
                    check=True,
                    capture_output=True,
                )
                resp_time = findall(r"time=.+m?s", shell.stdout, MULTILINE)[0].replace(
                    "time=", ""
                )
                text += f"    <b>{dc.upper()}:</b> {resp_time} {E_CHECK}\n"
            except Exception:
                text += f"    <b>{dc.upper()}:</b> {E_CROSS}\n"
        await edit_safe(m, text, reply_markup=contact_button)