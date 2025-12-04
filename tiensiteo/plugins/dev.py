import asyncio
import contextlib
import html
import io
import json
import os
import pickle
import platform
import re
import sys
import traceback
import logging
from logging import getLogger
from datetime import datetime
from inspect import getfullargspec
from shutil import disk_usage
from time import time
from typing import Any, Optional, Tuple

import aiohttp
import cloudscraper
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from psutil import Process, boot_time, cpu_count, cpu_percent
from psutil import disk_usage as disk_usage_percent
from psutil import net_io_counters, virtual_memory
from pyrogram import Client
from pyrogram import __version__ as pyrover
from pyrogram import enums, filters
from pyrogram.errors import (
    ChatSendPhotosForbidden,
    ChatSendPlainForbidden,
    FloodWait,
    MessageTooLong,
    PeerIdInvalid,
)
from pyrogram.raw.types import UpdateBotStopped
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from database.gban_db import add_gban_user, is_gbanned_user, remove_gban_user
from database.users_chats_db import db
from tiensiteo import BOT_NAME, app, botStartTime, tiensiteo_version, user
from tiensiteo.core.decorator import new_task
from tiensiteo.helper.eval_helper import format_exception, meval
from tiensiteo.helper.functions import extract_user, extract_user_and_reason
from tiensiteo.helper.http import fetch
from tiensiteo.helper.human_read import get_readable_file_size, get_readable_time
from tiensiteo.helper.localization import use_chat_lang
from tiensiteo.vars import AUTO_RESTART, COMMAND_HANDLER, LOG_CHANNEL, SUDO

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "LệnhChoDev"
__HELP__ = """
**Chỉ dành cho chủ sở hữu bot.**
<blockquote>/run [args] - Chạy lệnh eval CMD  
/logs [int] - Kiểm tra nhật ký bot  
/dlogs [int] - Xóa nhật ký bot  
/shell [args] - Chạy lệnh Exec/Terminal CMD  
/disablechat [chat id] - Thêm nhóm vào danh sách đen  
/enablechat [chat id] - Xoá nhóm khỏi danh sách đen  
/banuser [chat id] - Cấm người dùng và chặn người dùng không thể sử dụng bot  
/unbanuser [chat id] - Bỏ cấm người dùng và cho phép họ sử dụng bot lại  
/gban [chat id] - Cấm người dùng trên toàn bộ nhóm  
/ungban [chat id] - Bỏ cấm người dùng trên toàn bộ nhóm  
/restart - Cập nhật và khởi động lại bot  

**Dành cho người dùng công khai**
/json - Gửi cấu trúc tin nhắn Telegram ở định dạng JSON sử dụng kiểu Pyrogram</blockquote>
"""

var = {}
teskode = {}


async def edit_or_reply(self, msg, **kwargs):
    func = msg.edit if not self.me.is_bot else msg.reply
    spec = getfullargspec(func.__wrapped__).args
    await func(**{k: v for k, v in kwargs.items() if k in spec})


@app.on_message(filters.command(["privacy"], COMMAND_HANDLER))
@use_chat_lang()
async def privacy_policy(self: Client, ctx: Message, strings):
    await ctx.reply_msg(strings("privacy_policy").format(botname=self.me.first_name), message_effect_id=5104841245755180586 if ctx.chat.type.value == "private" else None)


@app.on_message(filters.command(["stars"], COMMAND_HANDLER))
async def star_donation(self: Client, ctx: Message):
    amount = ctx.command[1] if len(ctx.command) == 2 and ctx.command[1].isdigit() else 5
    await self.send_invoice(
        ctx.chat.id,
        title="Ủng hộ Tiến Sĩ Tèo",
        description="Bạn có thể ủng hộ tôi qua việc tặng sao",
        currency="XTR",
        prices=[LabeledPrice(label="Ủng hộ", amount=amount)],
        message_thread_id=ctx.message_thread_id,
        payload="stars",
    )


@app.on_pre_checkout_query()
async def pre_checkout_query_handler(_: Client, query: PreCheckoutQuery):
    await query.answer(success=True)


@app.on_message(filters.private, group=3)
async def successful_payment_handler(_: Client, message: Message):
    if message.successful_payment:
        await message.reply(
            f"Cảm ơn vì đã ủng hộ <b>{message.successful_payment.total_amount} {message.successful_payment.currency}</b>! Your transaction ID is : <code>{message.successful_payment.telegram_payment_charge_id}</code>"
        )


@app.on_message(filters.command(["refund_star"], COMMAND_HANDLER))
async def refund_star_payment(client: Client, message: Message):
    if len(message.command) == 1:
        return await message.reply_msg(
            "Please input telegram_payment_charge_id after command."
        )
    trx_id = message.command[1]
    try:
        await client.refund_star_payment(message.from_user.id, trx_id)
        await message.reply_msg(
            f"Great {message.from_user.mention}, your stars has been refunded to your balance."
        )
    except Exception as e:
        await message.reply_msg(e)


@app.on_message(filters.command(["logs"], COMMAND_HANDLER) & filters.user(SUDO))
@use_chat_lang()
async def log_file(_, ctx: Message, strings):
    """Send log file as document"""
    msg = await ctx.reply_msg("<b>Đang đọc logs ...</b>", quote=True)
    
    if len(ctx.command) == 1:
        try:
            file_size = os.path.getsize("TeoLogs.txt")
            await ctx.reply_document(
                "TeoLogs.txt",
                caption=f"Log Bot\nKích cỡ: {get_readable_file_size(file_size)}",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                strings("cl_btn"),
                                f"close#{ctx.from_user.id}",
                            )
                        ]
                    ]
                ),
            )
            await msg.delete_msg()
        except Exception as e:
            await msg.edit_msg(f"Lỗi khi gửi logs: {str(e)}")
            
    elif len(ctx.command) == 2:
        val = ctx.text.split()
        tail = await shell_exec(f"tail -n {val[1]} -v TeoLogs.txt")
        try:
            with io.BytesIO(str.encode(tail[0])) as s:
                s.name = "Logs-Tail.txt"
                await ctx.reply_document(
                    s,
                    caption=f"{val[1]} dòng cuối Logs của bot",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    strings("cl_btn"),
                                    f"close#{ctx.from_user.id}",
                                )
                            ]
                        ]
                    ),
                )
            await msg.delete_msg()
        except Exception as e:
            await msg.edit_msg(f"Lỗi khi xử lý lệnh: {str(e)}")
            
    else:
        await msg.edit_msg("Không hỗ trợ kiểu")

@app.on_message(filters.command(["dlogs"], COMMAND_HANDLER) & filters.user(SUDO))
@use_chat_lang()
async def delete_logs(_, ctx: Message, strings):
    """Delete log file content"""
    msg = await ctx.reply_msg("<b>Đang xử lý xóa log ...</b>", quote=True)
    try:
        # Ghi đè file log bằng file rỗng
        with open("TeoLogs.txt", "w") as file:
            file.write("")
        await msg.edit_msg("File logs được xóa thành công!")
    except Exception as e:
        await msg.edit_msg(f"Lỗi khi xóa logs: {str(e)}")


@app.on_message(filters.command(["donate"], COMMAND_HANDLER))
async def donate(self: Client, ctx: Message):
    try:
        await self.send_photo(
            ctx.chat.id,
            "https://api.dabeecao.org/data/tin-toi-di.jpg",
            caption="Xin chào, Nếu bạn thấy bot này hữu ích, bạn có thể quyên góp vào tài khoản bên dưới. Bởi vì bot này chạy trên server không miễn phí. Cảm ơn.\n\n<b>Các phương thức ủng hộ:</b>\n<b>Momo:</b> https://me.momo.vn/lDIjiWsjuDtos8TNi3IJ (Cao Duy Anh)\n<b>Ngân hàng Vietinbank, MBBank, OCB:</b> 0869261804 (Cao Duy Anh)\n\nHoặc ủng hộ qua Paypal tại địa chỉ:\nhttps://paypal.me/dabeecao",
            reply_to_message_id=ctx.id,
            message_effect_id=5159385139981059251
            if ctx.chat.type.value == "private"
            else None,
        )
    except (ChatSendPlainForbidden, ChatSendPhotosForbidden):
        await self.send_message(
            LOG_CHANNEL,
            f"❗️ <b>WARNING</b>\nI'm leaving from {ctx.chat.id} since i didn't have sufficient admin permissions.",
        )
        await ctx.chat.leave()

@app.on_message(filters.command(["stats"], COMMAND_HANDLER) & filters.user(SUDO))
@new_task
async def server_stats(_, ctx: Message) -> "Message":
    """
    Give system stats of the server.
    """
    total, used, free = disk_usage(".")
    process = Process(os.getpid())

    botuptime = get_readable_time(time() - botStartTime)
    osuptime = get_readable_time(time() - boot_time())
    currentTime = get_readable_time(time() - botStartTime)
    botusage = f"{round(process.memory_info()[0]/1024 ** 2)} MB"

    upload = get_readable_file_size(net_io_counters().bytes_sent)
    download = get_readable_file_size(net_io_counters().bytes_recv)

    cpu_percentage = cpu_percent()
    cpu_counts = cpu_count()

    ram_percentage = virtual_memory().percent
    ram_total = get_readable_file_size(virtual_memory().total)
    ram_used = get_readable_file_size(virtual_memory().used)

    disk_percenatge = disk_usage_percent("/").percent
    disk_total = get_readable_file_size(total)
    disk_used = get_readable_file_size(used)
    disk_free = get_readable_file_size(free)

    neofetch = (await shell_exec("neofetch --stdout"))[0]

    caption = f"<b>{BOT_NAME} {tiensiteo_version} is Up and Running successfully.</b>\n\n<code>{neofetch}</code>\n\n**OS Uptime:** <code>{osuptime}</code>\n<b>Bot Uptime:</b> <code>{currentTime}</code>\n**Bot Usage:** <code>{botusage}</code>\n\n**Total Space:** <code>{disk_total}</code>\n**Free Space:** <code>{disk_free}</code>\n\n**Download:** <code>{download}</code>\n**Upload:** <code>{upload}</code>\n\n<b>PyroFork Version</b>: <code>{pyrover}</code>\n<b>Python Version</b>: <code>{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} {sys.version_info[3].title()}</code>"

    if "oracle" in platform.uname().release:
        return await ctx.reply_msg(caption, quote=True)

    start = datetime.now()
    msg = await ctx.reply_photo(
        photo="https://te.legra.ph/file/30a82c22854971d0232c7.jpg",
        caption=caption,
        quote=True,
    )
    end = datetime.now()

    image = Image.open("assets/statsbg.jpg").convert("RGB")
    IronFont = ImageFont.truetype("assets/IronFont.otf", 42)
    draw = ImageDraw.Draw(image)

    def draw_progressbar(coordinate, progress):
        progress = 110 + (progress * 10.8)
        draw.ellipse((105, coordinate - 25, 127, coordinate), fill="#FFFFFF")
        draw.rectangle((120, coordinate - 25, progress, coordinate), fill="#FFFFFF")
        draw.ellipse(
            (progress - 7, coordinate - 25, progress + 15, coordinate), fill="#FFFFFF"
        )

    draw_progressbar(243, int(cpu_percentage))
    draw.text(
        (225, 153),
        f"( {cpu_counts} core, {cpu_percentage}% )",
        (255, 255, 255),
        font=IronFont,
    )

    draw_progressbar(395, int(disk_percenatge))
    draw.text(
        (335, 302),
        f"( {disk_used} / {disk_total}, {disk_percenatge}% )",
        (255, 255, 255),
        font=IronFont,
    )

    draw_progressbar(533, int(ram_percentage))
    draw.text(
        (225, 445),
        f"( {ram_used} / {ram_total} , {ram_percentage}% )",
        (255, 255, 255),
        font=IronFont,
    )

    draw.text((335, 600), f"{botuptime}", (255, 255, 255), font=IronFont)
    draw.text(
        (857, 607),
        f"{(end-start).microseconds/1000} ms",
        (255, 255, 255),
        font=IronFont,
    )

    image.save("stats.png")
    await msg.edit_media(media=InputMediaPhoto("stats.png", caption=caption))
    os.remove("stats.png")


# Gban
@app.on_message(filters.command("gban", COMMAND_HANDLER) & filters.user(SUDO))
async def ban_globally(self: Client, ctx: Message):
    user_id, reason = await extract_user_and_reason(ctx)
    if not user_id:
        return await ctx.reply_text("Tôi không thể tìm thấy người dùng đó.")
    if not reason:
        return await ctx.reply("Không có lý do được cung cấp.")

    try:
        getuser = await app.get_users(user_id)
        user_mention = getuser.mention
        user_id = getuser.id
    except PeerIdInvalid:
        user_mention = int(user_id)
        user_id = int(user_id)

    from_user = ctx.from_user

    if user_id in [from_user.id, self.me.id] or user_id in SUDO:
        return await ctx.reply_text("Tôi không thể cấm người dùng đó.")
    served_chats = await db.get_all_chats()
    m = await ctx.reply_text(
        f"**Cấm {user_mention} Toàn bộ! Việc này có thể mất nhiều thời gian.**"
    )
    await add_gban_user(user_id)
    number_of_chats = 0
    async for served_chat in served_chats:
        try:
            await app.ban_chat_member(served_chat["id"], user_id)
            number_of_chats += 1
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(int(e.value))
        except Exception:
            pass
    with contextlib.suppress(Exception):
        await app.send_message(
            user_id,
            f"Xin chào, Bạn đã bị cấm trên toàn cầu bởi {from_user.mention}, Bạn có thể kháng cáo lệnh cấm này bằng cách nói chuyện với anh ấy.",
        )
    await m.edit(f"Đã cấm {user_mention} toàn cầu!")
    ban_text = f"""
__**New Global Ban**__
**Origin:** {ctx.chat.title} [`{ctx.chat.id}`]
**Admin:** {from_user.mention}
**Banned User:** {user_mention}
**Banned User ID:** `{user_id}`
**Reason:** __{reason}__
**Chats:** `{number_of_chats}`"""
    try:
        m2 = await app.send_message(
            LOG_CHANNEL,
            text=ban_text,
            disable_web_page_preview=True,
        )
        await m.edit(
            f"Đã cấm {user_mention} toàn cầu!\nNhật ký hành động: {m2.link}",
            disable_web_page_preview=True,
        )
    except Exception:
        await ctx.reply_text(
            "Người Dùng Đã Bị Cấm, Nhưng Hành Động Gban Này Không Được Ghi Lại, Thêm Tôi Vào LOG_CHANNEL"
        )


# Ungban
@app.on_message(filters.command("ungban", COMMAND_HANDLER) & filters.user(SUDO))
async def unban_globally(_, ctx: Message):
    user_id = await extract_user(ctx)
    if not user_id:
        return await ctx.reply_text("Tôi không thể tìm thấy người dùng đó.")
    try:
        getuser = await app.get_users(user_id)
        user_mention = getuser.mention
        user_id = getuser.id
    except PeerIdInvalid:
        user_mention = int(user_id)
        user_id = int(user_id)

    is_gbanned = await is_gbanned_user(user_id)
    if not is_gbanned:
        await ctx.reply_text("Tôi không nhớ đã cấm anh ấy.")
    else:
        await remove_gban_user(user_id)
        await ctx.reply_text(f"Đã bỏ lệnh cấm {user_mention}.'")


@app.on_message(
    filters.command(["shell", "sh", "term"], COMMAND_HANDLER) & filters.user(SUDO)
)
@app.on_edited_message(
    filters.command(["shell", "sh", "term"], COMMAND_HANDLER)
    & filters.user(SUDO)
    & ~filters.react
)
@user.on_message(filters.command(["shell", "sh", "term"], ".") & filters.me)
@use_chat_lang()
async def shell_cmd(self: Client, ctx: Message, strings):
    if len(ctx.command) == 1:
        return await edit_or_reply(self, ctx, text=strings("no_cmd"))
    msg = (
        await ctx.edit_msg(strings("run_exec"))
        if not self.me.is_bot
        else await ctx.reply_msg(strings("run_exec"))
    )
    shell = (await shell_exec(ctx.input))[0]
    if len(shell) > 3000:
        with io.BytesIO(str.encode(shell)) as doc:
            doc.name = "shell_output.txt"
            await ctx.reply_document(
                document=doc,
                caption=f"<code>{ctx.input[: 4096 // 4 - 1]}</code>",
                file_name=doc.name,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text=strings("cl_btn"),
                                callback_data=f"close#{ctx.from_user.id if ctx.from_user else self.me.id}",
                            )
                        ]
                    ]
                ),
            )
            await msg.delete_msg()
    elif len(shell) != 0:
        await edit_or_reply(
            self,
            ctx,
            text=html.escape(shell),
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=strings("cl_btn"),
                            callback_data=f"close#{ctx.from_user.id if ctx.from_user else self.me.id}",
                        )
                    ]
                ]
            ),
        )
        if self.me.is_bot:
            await msg.delete_msg()
    else:
        await ctx.reply_msg(strings("no_reply"), del_in=5)


@app.on_message(
    (
        filters.command(["ev", "run", "myeval"], COMMAND_HANDLER)
        | filters.regex(r"app.run\(\)$")
    )
    & filters.user(SUDO)
)
@app.on_edited_message(
    (
        filters.command(["ev", "run", "meval"], COMMAND_HANDLER)
        | filters.regex(r"app.run\(\)$")
    )
    & filters.user(SUDO)
    & ~filters.react
)
@user.on_message(filters.command(["ev", "run", "meval"], ".") & filters.me)
@use_chat_lang()
async def cmd_eval(self: Client, ctx: Message, strings) -> Optional[str]:
    if (ctx.command and len(ctx.command) == 1) or ctx.text == "app.run()":
        return await edit_or_reply(self, ctx, text=strings("no_eval"))
    status_message = (
        await ctx.edit_msg(strings("run_eval"))
        if not self.me.is_bot
        else await ctx.reply_msg(strings("run_eval"), quote=True)
    )
    code = (
        ctx.text.split(maxsplit=1)[1]
        if ctx.command
        else ctx.text.split("\napp.run()")[0]
    )
    out_buf = io.StringIO()
    out = ""
    humantime = get_readable_time

    async def _eval() -> Tuple[str, Optional[str]]:
        # Message sending helper for convenience
        async def send(*args: Any, **kwargs: Any) -> Message:
            return await ctx.reply_msg(*args, **kwargs)

        # Print wrapper to capture output
        # We don't override sys.stdout to avoid interfering with other output
        def _print(*args: Any, **kwargs: Any) -> None:
            if "file" not in kwargs:
                kwargs["file"] = out_buf
            return print(*args, **kwargs)

        def _help(*args: Any, **kwargs: Any) -> None:
            with contextlib.redirect_stdout(out_buf):
                help(*args, **kwargs)

        eval_vars = {
            "self": self,
            "humantime": humantime,
            "ctx": ctx,
            "var": var,
            "teskode": teskode,
            "re": re,
            "os": os,
            "asyncio": asyncio,
            "cloudscraper": cloudscraper,
            "json": json,
            "aiohttp": aiohttp,
            "print": _print,
            "send": send,
            "stdout": out_buf,
            "traceback": traceback,
            "fetch": fetch,
            "r": ctx.reply_to_message,
            "requests": requests,
            "soup": BeautifulSoup,
            "h": _help,
        }
        eval_vars.update(var)
        eval_vars.update(teskode)
        try:
            return "", await meval(code, globals(), **eval_vars)
        except Exception as e:  # skipcq: PYL-W0703
            # Find first traceback frame involving the snippet
            first_snip_idx = -1
            tb = traceback.extract_tb(e.__traceback__)
            for i, frame in enumerate(tb):
                if frame.filename == "<string>" or frame.filename.endswith("ast.py"):
                    first_snip_idx = i
                    break
            # Re-raise exception if it wasn't caused by the snippet
            # Return formatted stripped traceback
            stripped_tb = tb[first_snip_idx:]
            formatted_tb = format_exception(e, tb=stripped_tb)
            return "⚠️ Error while executing snippet\n\n", formatted_tb

    before = time()
    prefix, result = await _eval()
    after = time()
    # Always write result if no output has been collected thus far
    if not out_buf.getvalue() or result is not None:
        print(result, file=out_buf)
    el_us = after - before
    try:
        el_str = get_readable_time(el_us)
    except:
        el_str = "1s"
    if not el_str or el_str is None:
        el_str = "0.1s"

    out = out_buf.getvalue()
    # Strip only ONE final newline to compensate for our message formatting
    if out.endswith("\n"):
        out = out[:-1]
    final_output = f"{prefix}<b>INPUT:</b>\n<pre language='python'>{html.escape(code)}</pre>\n<b>OUTPUT:</b>\n<pre language='python'>{html.escape(out)}</pre>\nThời gian thực hiện: {el_str}"
    if len(final_output) > 4096:
        with io.BytesIO(str.encode(out)) as out_file:
            out_file.name = "TienSiTeoEval.txt"
            await ctx.reply_document(
                document=out_file,
                caption=f"<code>{code[: 4096 // 4 - 1]}</code>",
                disable_notification=True,
                thumb="assets/thumb.jpg",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text=strings("cl_btn"),
                                callback_data=f"close#{ctx.from_user.id if ctx.from_user else self.me.id}",
                            )
                        ]
                    ]
                ),
            )
            await status_message.delete_msg()
    else:
        await edit_or_reply(
            self,
            ctx,
            text=final_output,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=strings("cl_btn"),
                            callback_data=f"close#{ctx.from_user.id if ctx.from_user else self.me.id}",
                        )
                    ]
                ]
            ),
        )
        if self.me.is_bot:
            await status_message.delete_msg()


# Update and restart bot
@app.on_message(filters.command(["restart"], COMMAND_HANDLER) & filters.user(SUDO))
@use_chat_lang()
async def update_restart(_, ctx: Message, strings):
    msg = await ctx.reply_msg(strings("up_and_rest"))
    with open("restart.pickle", "wb") as status:
        pickle.dump([ctx.chat.id, msg.id], status)
    os.execvp(sys.executable, [sys.executable, "-m", "tiensiteo"])


@app.on_poll(filters.chat(-1001777794636), group=-5)
async def tespoll(self, msg):
    await ctx.reply(msg)


@app.on_raw_update(group=-99)
async def updtebot(client, update, users, _):
    if isinstance(update, UpdateBotStopped):
        niuser = users[update.user_id]
        if update.stopped and await db.is_user_exist(niuser.id):
            await db.delete_user(niuser.id)
        await client.send_msg(
            LOG_CHANNEL,
            f"<a href='tg://user?id={niuser.id}'>{niuser.first_name}</a> (<code>{niuser.id}</code>) "
            f"{'BLOCKED' if update.stopped else 'UNBLOCKED'} the bot at "
            f"{datetime.fromtimestamp(update.date)}",
        )


async def aexec(code, c, m):
    exec(
        "async def __aexec(c, m): "
        + "\n p = print"
        + "\n replied = m.reply_to_message"
        + "".join(f"\n {l_}" for l_ in code.split("\n"))
    )
    return await locals()["__aexec"](c, m)


async def shell_exec(code, treat=True):
    process = await asyncio.create_subprocess_shell(
        code, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )

    stdout = (await process.communicate())[0]
    if treat:
        stdout = stdout.decode().strip()
    return stdout, process


async def auto_restart():
    os.execvp(sys.executable, [sys.executable, "-m", "tiensiteo"])


if AUTO_RESTART:
    scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.add_job(auto_restart, trigger="interval", days=3)
    scheduler.start()
