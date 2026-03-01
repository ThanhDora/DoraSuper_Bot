import html
import json
import re
import traceback
import logging
from logging import getLogger

from sys import platform
from sys import version as pyver

from bs4 import BeautifulSoup
from pykeyboard import InlineButton, InlineKeyboard
from pyrogram import __version__ as pyrover
from pyrogram import enums, filters
from pyrogram.errors import MessageIdInvalid, MessageNotModified
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent,
)

from dorasuper import BOT_USERNAME, app, user
from dorasuper.helper import GENRES_EMOJI, fetch, post_to_telegraph, search_jw
from dorasuper.plugins.dev import shell_exec
from dorasuper.vars import USER_SESSION
from utils import demoji

LOGGER = getLogger("DoraSuper")

__MODULE__ = "TínhNăngInline"
__HELP__ = """
<blockquote>Để sử dụng tính năng này, chỉ cần gõ tên bot (ví dụ: @caoteo_bot) kèm theo các tham số sau:
/laythongtin [ID người dùng/tên người dùng] - Kiểm tra thông tin về một người dùng.
/tinbaomat [nội_dung:] - Gửi tin nhắn bảo mật cho người khác, kết thúc bằng dấu "." để hoàn tất.
/git [truy vấn] - Tìm kiếm và lấy thông tin project trên Github.</blockquote>
"""

keywords_list = ["tinbaomat", "laythongtin", "git"]

PRVT_MSGS = {}


@app.on_inline_query()
async def inline_menu(self, inline_query: InlineQuery):
    if inline_query.query.strip().lower().strip() == "":
        buttons = InlineKeyboard(row_width=2)
        buttons.add(
            *[
                (InlineKeyboardButton(text=i, switch_inline_query_current_chat=i))
                for i in keywords_list
            ]
        )

        btn = InlineKeyboard(row_width=1)
        btn.add(
            InlineKeyboardButton("Go Inline!", switch_inline_query_current_chat=""),
        )

        answerss = [
            InlineQueryResultArticle(
                title="Lệnh Inline",
                description="Trợ giúp cách dùng các lệnh Inline.",
                input_message_content=InputTextMessageContent(
                    "Chọn một nút để bắt đầu sử dụng tính năng Inline.\n\n\ntinbaomat - Gửi tin nhắn bảo mật đến người dùng cụ thể, chỉ người được chỉ định mới có thể xem.\n\nlaythongtin - Lấy thông tin về tài khoản Telegram bằng ID hoặc Username.\n\ngit - Lấy thông tin của project cụ thể trên Github."
                ),
                thumb_url="https://api.dabeecao.org/data/teo_em_bot.jpg",
                reply_markup=buttons,
            ),
        ]
        await inline_query.answer(results=answerss)
        
    elif inline_query.query.strip().lower().split()[0] == "laythongtin":
        if len(inline_query.query.strip().lower().split()) < 2:
            return await inline_query.answer(
                results=[],
                switch_pm_text="Tìm thông tin người dùng | laythongtin [id/username]",
                switch_pm_parameter="inline",
            )
        userr = inline_query.query.split(None, 1)[1].strip()
        
        # Kiểm tra xem `userr` có phải là một ID hay không
        try:
            user_id = int(userr)
            diaa = await app.get_users(user_id)
        except ValueError:
            # Nếu không phải là ID, xử lý như username
            if "t.me" in userr:
                r = re.search(r"t.me/(\w+)", userr)
                userr = r[1]
            diaa = await app.get_users(userr)
        except Exception:  # pylint: disable=broad-except
            inline_query.stop_propagation()
            return
    
        namanya = (
            f"{diaa.first_name} {diaa.last_name}" if diaa.last_name else diaa.first_name
        )
        msg = f"<b>🏷 Tên:</b> {namanya}\n<b>🆔 ID:</b> <code>{diaa.id}</code>\n"
        if diaa.username:
            msg += f"<b>🌐 Tên người dùng:</b> <code>@{diaa.username}</code>\n"
        if diaa.status:
            msg += f"<b>🕰 Trạng thái người dùng:</b> {diaa.status}\n"
        if diaa.dc_id:
            msg += f"<b>🌏 DC:</b> {diaa.dc_id}\n"
        msg += f"<b>✨ Premium:</b> {diaa.is_premium}\n"
        msg += f"<b>⭐️ Đã xác minh:</b> {diaa.is_verified}\n"
        msg += f"<b>🤖 Bot:</b> {diaa.is_bot}\n"
        if diaa.language_code:
            msg += f"<b>🇮🇩 Ngôn ngữ:</b> {diaa.language_code}"
        
        results = [
            InlineQueryResultArticle(
                title=f"Lấy thông tin của {diaa.id}",
                input_message_content=InputTextMessageContent(msg),
                description=f"Lấy thông tin của {diaa.id}",
            )
        ]
        await inline_query.answer(results=results, cache_time=3)
    elif inline_query.query.strip().lower().split()[0] == "tinbaomat":
        if len(inline_query.query.strip().lower().split()) < 3:
            return await inline_query.answer(
                results=[],
                switch_pm_text="Tin nhắn bảo mật | tinbaomat [USERNAME/ID] [NỘI_DUNG.]",
                switch_pm_parameter="inline",
            )
        _id = inline_query.query.split()[1]
        msg = inline_query.query.split(None, 2)[2].strip()
    
        if not msg or not msg.endswith("."):
            inline_query.stop_propagation()
            return  # Thêm return để dừng hàm nếu điều kiện không thỏa mãn
    
        try:
            # Kiểm tra nếu `_id` là ID hay username
            try:
                user_id = int(_id)
                penerima = await app.get_users(user_id)
            except ValueError:
                # Nếu không phải là ID, xử lý như username
                if "t.me" in _id:
                    r = re.search(r"t.me/(\w+)", _id)
                    _id = r[1]
                penerima = await app.get_users(_id)
        except Exception:  # pylint: disable=broad-except
            inline_query.stop_propagation()
            return
    
        PRVT_MSGS[inline_query.id] = (
            penerima.id,
            penerima.first_name,
            inline_query.from_user.id,
            msg.strip(". "),
        )
        prvte_msg = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Hiển thị tin nhắn 🔐", callback_data=f"prvtmsg({inline_query.id})"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Hủy tin nhắn ☠️",
                        callback_data=f"destroy({inline_query.id})",
                    )
                ],
            ]
        )
        mention = (
            f"@{penerima.username}"
            if penerima.username
            else f"<a href='tg://user?id={penerima.id}'>{penerima.first_name}</a>"
        )
        msg_c = (
            f"🔒 Đã gửi <b>Tin nhắn bảo mật</b> tới {mention} [<code>{penerima.id}</code>], "
        )
        msg_c += "Chỉ người đó mới có thể xem tin nhắn này."
        results = [
            InlineQueryResultArticle(
                title=f"Gửi một tin nhắn bảo mật tới {penerima.first_name}",
                input_message_content=InputTextMessageContent(msg_c),
                description="Chỉ người đó mới có thể xem tin nhắn.",
                thumb_url="https://api.dabeecao.org/data/teo_em_bot.jpg",
                reply_markup=prvte_msg,
            )
        ]
        await inline_query.answer(results=results, cache_time=3)
    elif inline_query.query.strip().lower().split()[0] == "git":
        if len(inline_query.query.strip().lower().split()) < 2:
            return await inline_query.answer(
                results=[],
                switch_pm_text="Tìm kiếm project Github | git [truy_vấn]",
                switch_pm_parameter="inline",
            )
        query = inline_query.query.split(None, 1)[1].strip()
        search_results = await fetch.get(
            f"https://api.github.com/search/repositories?q={query}"
        )
        srch_results = json.loads(search_results.text)
        item = srch_results.get("items")
        data = []
        for result in item:
            title = result.get("full_name")
            link = result.get("html_url")
            desc = result.get("description") if result.get("description") else ""
            deskripsi = desc[:100] if len(desc) > 100 else desc
            lang = result.get("language")
            message_text = f"🔗: {result.get('html_url')}\n│\n└─🍴Forks: {result.get('forks')}    ┃┃    🌟Stars: {result.get('stargazers_count')}\n\n"
            message_text += f"<b>Mô tả:</b> {deskripsi}\n"
            message_text += f"<b>Ngôn ngữ:</b> {lang}"
            data.append(
                InlineQueryResultArticle(
                    title=f"{title}",
                    input_message_content=InputTextMessageContent(
                        message_text=message_text,
                        parse_mode=enums.ParseMode.HTML,
                        disable_web_page_preview=False,
                    ),
                    url=link,
                    description=deskripsi,
                    thumb_url="https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton(text="Xem trên Github", url=link)]]
                    ),
                )
            )
        await inline_query.answer(
            results=data,
            is_gallery=False,
            is_personal=False,
            next_offset="",
            switch_pm_text=f"Tìm thấy {len(data)} kết quả",
            switch_pm_parameter="github",
        )

@app.on_callback_query(filters.regex(r"prvtmsg\((.+)\)"))
async def prvt_msg(_, c_q):
    msg_id = str(c_q.matches[0].group(1))

    if msg_id not in PRVT_MSGS:
        await c_q.answer("Tin nhắn hiện đã hết thời gian xem !", show_alert=True)
        return

    user_id, flname, sender_id, msg = PRVT_MSGS[msg_id]

    if c_q.from_user.id in (user_id, sender_id):
        await c_q.answer(msg, show_alert=True)
    else:
        await c_q.answer(f"Chỉ {flname} có thể xem tin nhắn bảo mật này!", show_alert=True)


@app.on_callback_query(filters.regex(r"destroy\((.+)\)"))
async def destroy_msg(_, c_q):
    msg_id = str(c_q.matches[0].group(1))

    if msg_id not in PRVT_MSGS:
        await c_q.answer("Tin nhắn đã hết thời gian !", show_alert=True)
        return

    user_id, flname, sender_id, _ = PRVT_MSGS[msg_id]

    if c_q.from_user.id in (user_id, sender_id):
        del PRVT_MSGS[msg_id]
        by = "người nhận." if c_q.from_user.id == user_id else "người gửi."
        await c_q.edit_message_text(f"Tin nhắn Bảo Mật này đã bị Hủy ☠️ bởi {by}")
    else:
        await c_q.answer(f"Chỉ {flname} có thể hủy tin nhắn Bảo Mật này!", show_alert=True)