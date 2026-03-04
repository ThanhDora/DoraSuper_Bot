import os
import re
import time
import logging
from logging import getLogger

from pyrogram import Client, enums, filters
from pyrogram.types import Message

from dorasuper.emoji import E_AFK
from dorasuper.vars import COMMAND_HANDLER, SUDO


from database.afk_db import add_afk, cleanmode_off, cleanmode_on, is_afk, remove_afk
from dorasuper import app
from dorasuper.core.decorator.permissions import adminsOnly
from dorasuper.helper import get_readable_time2
from dorasuper.helper.emoji_fmt import EMOJI_FMT
from dorasuper.helper.localization import use_chat_lang
from utils import put_cleanmode

LOGGER = getLogger("DoraSuper")

__MODULE__ = "AFK"
__HELP__ = """
<blockquote>/afk [Lý do > Tùy chọn] - Thông báo cho người khác rằng bạn đang AFK (Away From Keyboard - Rời khỏi bàn phím), để bạn trai hoặc bạn gái của bạn không tìm kiếm bạn 💔.
/afk [trả lời phương tiện truyền thông] - AFK kèm với phương tiện truyền thông.
/afkdel - Bật tự động xóa tin nhắn AFK trong nhóm (Chỉ dành cho quản trị viên nhóm). Mặc định là Bật.
Chỉ cần gõ gì đó trong nhóm để xóa trạng thái AFK.</blockquote>
"""


# Handle set AFK Command
@app.on_cmd("afk")
@use_chat_lang()
async def active_afk(_, ctx: Message, strings):
    if ctx.sender_chat:
        return await ctx.reply_msg(strings("no_channel").format(**EMOJI_FMT), del_in=6)
    user_id = ctx.from_user.id
    verifier, reasondb = await is_afk(user_id)
    if verifier:
        await remove_afk(user_id)
        try:
            afktype = reasondb["type"]
            timeafk = reasondb["time"]
            data = reasondb["data"]
            reasonafk = reasondb["reason"]
            seenago = get_readable_time2((int(time.time() - timeafk)))
            if afktype == "animation":
                send = (
                    await ctx.reply_animation(
                        data,
                        caption=strings("on_afk_msg_no_r").format(
                            usr=ctx.from_user.mention, id=ctx.from_user.id, tm=seenago, **EMOJI_FMT
                        ),
                    )
                    if str(reasonafk) == "None"
                    else await ctx.reply_animation(
                        data,
                        caption=strings("on_afk_msg_with_r").format(
                            usr=ctx.from_user.mention,
                            id=ctx.from_user.id,
                            tm=seenago,
                            reas=reasonafk,
                            **EMOJI_FMT,
                        ),
                    )
                )
            elif afktype == "video":
                send = (
                    await ctx.reply_video(
                        data,
                        caption=strings("on_afk_msg_no_r").format(
                            usr=ctx.from_user.mention, id=ctx.from_user.id, tm=seenago, **EMOJI_FMT
                        ),
                    )
                    if str(reasonafk) == "None"
                    else await ctx.reply_video(
                        data,
                        caption=strings("on_afk_msg_with_r").format(
                            usr=ctx.from_user.mention,
                            id=ctx.from_user.id,
                            tm=seenago,
                            reas=reasonafk,
                            **EMOJI_FMT,
                        ),
                    )
                )
            elif afktype == "photo":
                send = (
                    await ctx.reply_photo(
                        photo=f"downloads/{user_id}.jpg",
                        caption=strings("on_afk_msg_no_r").format(
                            usr=ctx.from_user.mention, id=ctx.from_user.id, tm=seenago, **EMOJI_FMT
                        ),
                    )
                    if str(reasonafk) == "None"
                    else await ctx.reply_photo(
                        photo=f"downloads/{user_id}.jpg",
                        caption=strings("on_afk_msg_with_r").format(
                            usr=ctx.from_user.first_name, id=ctx.from_user.id, tm=seenago, reas=reasonafk, **EMOJI_FMT
                        ),
                    )
                )
            elif afktype == "text":
                send = await ctx.reply_text(
                    strings("on_afk_msg_no_r").format(
                        usr=ctx.from_user.mention, id=ctx.from_user.id, tm=seenago, **EMOJI_FMT
                    ),
                    disable_web_page_preview=True,
                )
            elif afktype == "text_reason":
                send = await ctx.reply_text(
                    strings("on_afk_msg_with_r").format(
                        usr=ctx.from_user.mention,
                        id=ctx.from_user.id,
                        tm=seenago,
                        reas=reasonafk,
                        **EMOJI_FMT,
                    ),
                    disable_web_page_preview=True,
                )
        except Exception:
            send = await ctx.reply_text(
                strings("is_online").format(
                    usr=ctx.from_user.first_name, id=ctx.from_user.id, **EMOJI_FMT
                ),
                disable_web_page_preview=True,
            )
        await put_cleanmode(ctx.chat.id, send.id)
        return
    if len(ctx.command) == 1 and not ctx.reply_to_message:
        details = {
            "type": "text",
            "time": time.time(),
            "data": None,
            "reason": None,
        }
    elif len(ctx.command) > 1 and not ctx.reply_to_message:
        _reason = (ctx.text.split(None, 1)[1].strip())[:100]
        details = {
            "type": "text_reason",
            "time": time.time(),
            "data": None,
            "reason": _reason,
        }
    elif len(ctx.command) == 1 and ctx.reply_to_message.animation:
        _data = ctx.reply_to_message.animation.file_id
        details = {
            "type": "animation",
            "time": time.time(),
            "data": _data,
            "reason": None,
        }
    elif len(ctx.command) == 1 and ctx.reply_to_message.video:
        _data = ctx.reply_to_message.video.file_id
        details = {
            "type": "video",
            "time": time.time(),
            "data": _data,
            "reason": None,
        }
    elif len(ctx.command) > 1 and ctx.reply_to_message.video:
        _data = ctx.reply_to_message.video.file_id
        _reason = (ctx.text.split(None, 1)[1].strip())[:100]
        details = {
            "type": "video",
            "time": time.time(),
            "data": _data,
            "reason": _reason,
        }
    elif len(ctx.command) > 1 and ctx.reply_to_message.animation:
        _data = ctx.reply_to_message.animation.file_id
        _reason = (ctx.text.split(None, 1)[1].strip())[:100]
        details = {
            "type": "animation",
            "time": time.time(),
            "data": _data,
            "reason": _reason,
        }
    elif len(ctx.command) == 1 and ctx.reply_to_message.photo:
        os.makedirs("downloads", exist_ok=True)
        await app.download_media(ctx.reply_to_message, file_name=f"downloads/{user_id}.jpg")
        details = {
            "type": "photo",
            "time": time.time(),
            "data": None,
            "reason": None,
        }
    elif len(ctx.command) > 1 and ctx.reply_to_message.photo:
        os.makedirs("downloads", exist_ok=True)
        await app.download_media(ctx.reply_to_message, file_name=f"downloads/{user_id}.jpg")
        _reason = ctx.text.split(None, 1)[1].strip()
        details = {
            "type": "photo",
            "time": time.time(),
            "data": None,
            "reason": _reason,
        }
    elif len(ctx.command) == 1 and ctx.reply_to_message.sticker:
        if ctx.reply_to_message.sticker.is_animated:
            details = {
                "type": "text",
                "time": time.time(),
                "data": None,
                "reason": None,
            }
        else:
            os.makedirs("downloads", exist_ok=True)
            await app.download_media(ctx.reply_to_message, file_name=f"downloads/{user_id}.jpg")
            details = {
                "type": "photo",
                "time": time.time(),
                "data": None,
                "reason": None,
            }
    elif len(ctx.command) > 1 and ctx.reply_to_message.sticker:
        _reason = (ctx.text.split(None, 1)[1].strip())[:100]
        if ctx.reply_to_message.sticker.is_animated:
            details = {
                "type": "text_reason",
                "time": time.time(),
                "data": None,
                "reason": _reason,
            }
        else:
            os.makedirs("downloads", exist_ok=True)
            await app.download_media(ctx.reply_to_message, file_name=f"downloads/{user_id}.jpg")
            details = {
                "type": "photo",
                "time": time.time(),
                "data": None,
                "reason": _reason,
            }
    else:
        details = {
            "type": "text",
            "time": time.time(),
            "data": None,
            "reason": None,
        }

    await add_afk(user_id, details)
    send = await ctx.reply_msg(
        strings("now_afk").format(usr=ctx.from_user.mention, id=ctx.from_user.id, **EMOJI_FMT)
    )
    await put_cleanmode(ctx.chat.id, send.id)


@app.on_cmd("afkdel", group_only=True)
@adminsOnly("can_change_info")
@use_chat_lang()
async def afk_state(_, ctx: Message, strings):
    if not ctx.from_user:
        return
    if len(ctx.command) == 1:
        return await ctx.reply_msg(
            strings("afkdel_help").format(cmd=ctx.command[0], **EMOJI_FMT), del_in=6
        )
    chat_id = ctx.chat.id
    state = ctx.text.split(None, 1)[1].strip()
    state = state.lower()
    if state == "enable":
        await cleanmode_on(chat_id)
        await ctx.reply_msg(strings("afkdel_enable").format(**EMOJI_FMT))
    elif state == "disable":
        await cleanmode_off(chat_id)
        await ctx.reply_msg(strings("afkdel_disable").format(**EMOJI_FMT))
    else:
        await ctx.reply_msg(strings("afkdel_help").format(cmd=ctx.command[0], **EMOJI_FMT), del_in=6)


# Khi đang AFK, gửi bất kỳ tin nào trong private → tắt AFK
@app.on_message(filters.private & ~filters.bot & ~filters.via_bot, group=0)
@use_chat_lang()
async def afk_private_watcher(_, ctx: Message, strings):
    if not ctx.from_user:
        return
    userid = ctx.from_user.id
    verifier, _ = await is_afk(userid)
    if verifier:
        await remove_afk(userid)
        try:
            await ctx.reply_msg(
                strings("is_online").format(
                    usr=ctx.from_user.mention, id=userid, **EMOJI_FMT
                ),
                disable_web_page_preview=True,
            )
        except Exception:
            pass


# Khi bạn đang AFK, gõ bất kỳ tin nhắn nào (text, ảnh, sticker, ...) trong nhóm hoặc private → tắt AFK.
# Chỉ bỏ qua khi tin nhắn đúng là lệnh /afk (để dùng khi bật AFK).
@app.on_message(
    filters.group & ~filters.bot & ~filters.via_bot,
    group=0,
)
@use_chat_lang()
async def afk_watcher_func(self: Client, ctx: Message, strings):
    if ctx.sender_chat or not ctx.from_user:
        return
    userid = ctx.from_user.id
    user_name = ctx.from_user.mention
    message_text = (ctx.text or ctx.caption) or ""
    # Chỉ bỏ qua nếu đúng là lệnh /afk (hoặc !afk, /afk@bot)
    if ctx.entities and message_text:
        possible = ["/afk", f"/afk@{self.me.username}", "!afk"]
        for entity in ctx.entities:
            try:
                if entity.type == enums.MessageEntityType.BOT_COMMAND:
                    start = getattr(entity, "offset", 0)
                    end = start + getattr(entity, "length", 0)
                    if end <= len(message_text) and message_text[start:end].lower().strip() in possible:
                        return
            except (UnicodeDecodeError, IndexError):
                pass

    msg = ""
    send = None
    replied_user_id = 0

    # Bạn đang AFK mà gửi tin (bất kỳ) → tắt AFK và báo "đã trực tuyến"
    verifier, reasondb = await is_afk(userid)
    if verifier:
        await remove_afk(userid)
        try:
            afktype = reasondb["type"]
            timeafk = reasondb["time"]
            data = reasondb["data"]
            reasonafk = reasondb["reason"]
            seenago = get_readable_time2((int(time.time() - timeafk)))
            if afktype == "text":
                msg += strings("on_afk_msg_no_r").format(
                    usr=user_name, id=userid, tm=seenago, **EMOJI_FMT
                )
            if afktype == "text_reason":
                msg += strings("on_afk_msg_with_r").format(
                    usr=user_name, id=userid, tm=seenago, reas=reasonafk, **EMOJI_FMT
                )
            if afktype == "animation":
                if str(reasonafk) == "None":
                    send = await ctx.reply_animation(
                        data,
                        caption=strings("on_afk_msg_no_r").format(
                            usr=user_name, id=userid, tm=seenago, **EMOJI_FMT
                        ),
                    )
                else:
                    send = await ctx.reply_animation(
                        data,
                        caption=strings("on_afk_msg_with_r").format(
                            usr=user_name, id=userid, tm=seenago, reas=reasonafk, **EMOJI_FMT
                        ),
                    )
            if afktype == "video":
                if str(reasonafk) == "None":
                    send = await ctx.reply_video(
                        data,
                        caption=strings("on_afk_msg_no_r").format(
                            usr=user_name, id=userid, tm=seenago, **EMOJI_FMT
                        ),
                    )
                else:
                    send = await ctx.reply_video(
                        data,
                        caption=strings("on_afk_msg_with_r").format(
                            usr=user_name, id=userid, tm=seenago, reas=reasonafk, **EMOJI_FMT
                        ),
                    )
            if afktype == "photo":
                if str(reasonafk) == "None":
                    send = await ctx.reply_photo(
                        photo=f"downloads/{userid}.jpg",
                        caption=strings("on_afk_msg_no_r").format(
                            usr=user_name, id=userid, tm=seenago, **EMOJI_FMT
                        ),
                    )
                else:
                    send = await ctx.reply_photo(
                        photo=f"downloads/{userid}.jpg",
                        caption=strings("on_afk_msg_with_r").format(
                            usr=user_name, id=userid, tm=seenago, reas=reasonafk, **EMOJI_FMT
                        ),
                    )
        except Exception:
            msg += strings("is_online").format(usr=user_name, id=userid, **EMOJI_FMT)

    # Replied to a User which is AFK
    if ctx.reply_to_message:
        try:
            replied_first_name = ctx.reply_to_message.from_user.mention
            replied_user_id = ctx.reply_to_message.from_user.id
            verifier, reasondb = await is_afk(replied_user_id)
            if verifier:
                try:
                    afktype = reasondb["type"]
                    timeafk = reasondb["time"]
                    data = reasondb["data"]
                    reasonafk = reasondb["reason"]
                    seenago = get_readable_time2((int(time.time() - timeafk)))
                    if afktype == "text":
                        msg += strings("is_afk_msg_no_r").format(
                            usr=replied_first_name, id=replied_user_id, tm=seenago, **EMOJI_FMT
                        )
                    if afktype == "text_reason":
                        msg += strings("is_afk_msg_with_r").format(
                            usr=replied_first_name,
                            id=replied_user_id,
                            tm=seenago,
                            reas=reasonafk,
                            **EMOJI_FMT,
                        )
                    if afktype == "animation":
                        if str(reasonafk) == "None":
                            send = await ctx.reply_animation(
                                data,
                                caption=strings("is_afk_msg_no_r").format(
                                    usr=replied_first_name,
                                    id=replied_user_id,
                                    tm=seenago,
                                    **EMOJI_FMT,
                                ),
                            )
                        else:
                            send = await ctx.reply_animation(
                                data,
                                caption=strings("is_afk_msg_with_r").format(
                                    usr=replied_first_name,
                                    id=replied_user_id,
                                    tm=seenago,
                                    reas=reasonafk,
                                    **EMOJI_FMT,
                                ),
                            )
                    if afktype == "video":
                        if str(reasonafk) == "None":
                            send = await ctx.reply_video(
                                data,
                                caption=strings("is_afk_msg_no_r").format(
                                    usr=replied_first_name,
                                    id=replied_user_id,
                                    tm=seenago,
                                    **EMOJI_FMT,
                                ),
                            )
                        else:
                            send = await ctx.reply_video(
                                data,
                                caption=strings("is_afk_msg_with_r").format(
                                    usr=replied_first_name,
                                    id=replied_user_id,
                                    tm=seenago,
                                    reas=reasonafk,
                                    **EMOJI_FMT,
                                ),
                            )
                    if afktype == "photo":
                        if str(reasonafk) == "None":
                            send = await ctx.reply_photo(
                                photo=f"downloads/{replied_user_id}.jpg",
                                caption=strings("is_afk_msg_no_r").format(
                                    usr=replied_first_name,
                                    id=replied_user_id,
                                    tm=seenago,
                                    **EMOJI_FMT,
                                ),
                            )
                        else:
                            send = await ctx.reply_photo(
                                photo=f"downloads/{replied_user_id}.jpg",
                                caption=strings("is_afk_msg_with_r").format(
                                    usr=replied_first_name,
                                    id=replied_user_id,
                                    tm=seenago,
                                    reas=reasonafk,
                                    **EMOJI_FMT,
                                ),
                            )
                except Exception:
                    msg += strings("is_afk").format(
                        usr=replied_first_name, id=replied_user_id, **EMOJI_FMT
                    )
        except:
            pass

    # Khi user khác tag/mention bạn (bạn đang AFK) → bot báo "đang AFK"
    if ctx.entities and message_text:
        entity_list = ctx.entities
        for j in range(len(entity_list)):
            ent = entity_list[j]
            if ent.type == enums.MessageEntityType.MENTION:
                try:
                    start = getattr(ent, "offset", 0)
                    end = start + getattr(ent, "length", 0)
                    if end > len(message_text):
                        continue
                    mention_text = message_text[start:end].lstrip("@")
                    if not mention_text:
                        continue
                    user = await app.get_users(mention_text)
                    if user.id == replied_user_id:
                        continue
                except Exception:
                    continue
                verifier, reasondb = await is_afk(user.id)
                if verifier:
                    try:
                        afktype = reasondb["type"]
                        timeafk = reasondb["time"]
                        data = reasondb["data"]
                        reasonafk = reasondb["reason"]
                        seenago = get_readable_time2((int(time.time() - timeafk)))
                        if afktype == "text":
                            msg += strings("is_afk_msg_no_r").format(
                                usr=user.first_name[:25], id=user.id, tm=seenago, **EMOJI_FMT
                            )
                        if afktype == "text_reason":
                            msg += strings("is_afk_msg_with_r").format(
                                usr=user.first_name[:25],
                                id=user.id,
                                tm=seenago,
                                reas=reasonafk,
                                **EMOJI_FMT,
                            )
                        if afktype == "animation":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_animation(
                                    data,
                                    caption=strings("is_afk_msg_no_r").format(
                                        usr=user.first_name[:25], id=user.id, tm=seenago, **EMOJI_FMT
                                    ),
                                )
                            else:
                                send = await ctx.reply_animation(
                                    data,
                                    caption=strings("is_afk_msg_with_r").format(
                                        usr=user.first_name[:25],
                                        id=user.id,
                                        tm=seenago,
                                        reas=reasonafk,
                                        **EMOJI_FMT,
                                    ),
                                )
                        if afktype == "video":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_video(
                                    data,
                                    caption=strings("is_afk_msg_no_r").format(
                                        usr=user.first_name[:25], id=user.id, tm=seenago, **EMOJI_FMT
                                    ),
                                )
                            else:
                                send = await ctx.reply_video(
                                    data,
                                    caption=strings("is_afk_msg_with_r").format(
                                        usr=user.first_name[:25],
                                        id=user.id,
                                        tm=seenago,
                                        reas=reasonafk,
                                        **EMOJI_FMT,
                                    ),
                                )
                        if afktype == "photo":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_photo(
                                    photo=f"downloads/{user.id}.jpg",
                                    caption=strings("is_afk_msg_no_r").format(
                                        usr=user.first_name[:25], id=user.id, tm=seenago, **EMOJI_FMT
                                    ),
                                )
                            else:
                                send = await ctx.reply_photo(
                                    photo=f"downloads/{user.id}.jpg",
                                    caption=strings("is_afk_msg_with_r").format(
                                        usr=user.first_name[:25],
                                        id=user.id,
                                        tm=seenago,
                                        reas=reasonafk,
                                        **EMOJI_FMT,
                                    ),
                                )
                    except Exception:
                        msg += strings("is_afk").format(
                            usr=(user.first_name or "User")[:25], id=user.id, **EMOJI_FMT
                        )
            elif ent.type == enums.MessageEntityType.TEXT_MENTION:
                try:
                    user_id = ent.user.id
                    if user_id == replied_user_id:
                        continue
                    first_name = (ent.user.first_name or "User")[:25]
                except Exception:
                    continue
                verifier, reasondb = await is_afk(user_id)
                if verifier:
                    try:
                        afktype = reasondb["type"]
                        timeafk = reasondb["time"]
                        data = reasondb["data"]
                        reasonafk = reasondb["reason"]
                        seenago = get_readable_time2((int(time.time() - timeafk)))
                        if afktype == "text":
                            msg += strings("is_afk_msg_no_r").format(
                                usr=first_name[:25], id=user_id, tm=seenago, **EMOJI_FMT
                            )
                        if afktype == "text_reason":
                            msg += strings("is_afk_msg_with_r").format(
                                usr=first_name[:25],
                                id=user_id,
                                tm=seenago,
                                reas=reasonafk,
                                **EMOJI_FMT,
                            )
                        if afktype == "animation":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_animation(
                                    data,
                                    caption=strings("is_afk_msg_no_r").format(
                                        usr=first_name[:25], id=user_id, tm=seenago, **EMOJI_FMT
                                    ),
                                )
                            else:
                                send = await ctx.reply_animation(
                                    data,
                                    caption=strings("is_afk_msg_with_r").format(
                                        usr=first_name[:25],
                                        id=user_id,
                                        tm=seenago,
                                        reas=reasonafk,
                                        **EMOJI_FMT,
                                    ),
                                )
                        if afktype == "video":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_video(
                                    data,
                                    caption=strings("is_afk_msg_no_r").format(
                                        usr=first_name[:25], id=user_id, tm=seenago, **EMOJI_FMT
                                    ),
                                )
                            else:
                                send = await ctx.reply_video(
                                    data,
                                    caption=strings("is_afk_msg_with_r").format(
                                        usr=first_name[:25],
                                        id=user_id,
                                        tm=seenago,
                                        reas=reasonafk,
                                        **EMOJI_FMT,
                                    ),
                                )
                        if afktype == "photo":
                            if str(reasonafk) == "None":
                                send = await ctx.reply_photo(
                                    photo=f"downloads/{user_id}.jpg",
                                    caption=strings("is_afk_msg_no_r").format(
                                        usr=first_name[:25], id=user_id, tm=seenago, **EMOJI_FMT
                                    ),
                                )
                            else:
                                send = await ctx.reply_photo(
                                    photo=f"downloads/{user_id}.jpg",
                                    caption=strings("is_afk_msg_with_r").format(
                                        usr=first_name[:25],
                                        id=user_id,
                                        tm=seenago,
                                        reas=reasonafk,
                                        **EMOJI_FMT,
                                    ),
                                )
                    except Exception:
                        msg += strings("is_afk").format(usr=first_name, id=user_id, **EMOJI_FMT)
    if msg != "":
        try:
            send = await ctx.reply_text(msg, disable_web_page_preview=True)
        except Exception:
            pass
    if send is not None:
        try:
            await put_cleanmode(ctx.chat.id, send.id)
        except Exception:
            pass
