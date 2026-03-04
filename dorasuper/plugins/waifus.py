import asyncio
import html
import requests
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message
from dorasuper import app
from dorasuper.emoji import (
    E_BITE_YOUR_LIPS,
    E_CHECK,
    E_CRY,
    E_ERROR,
    E_EYE_ROLL,
    E_FIRE,
    E_GLARE,
    E_HEART,
    E_HEART2,
    E_HEART4,
    E_LOADING,
    E_PARTY,
    E_PENDING,
    E_ROCKET,
    E_SHOUT,
    E_SIDEWAYS,
    E_SUCCESS,
    E_SWEET,
    E_TIP,
    E_TYMMY,
    E_VIEW,
    E_VUAM,
    E_WAIT,
    E_WINK,
    E_WRENCH,
)
from dorasuper.core.decorator.errors import capture_err
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")

NEKOS_BEST_BASE = "https://nekos.best/api/v2"
NEKOS_UA = "DoraSuper/1.0 (https://github.com/DoraTeam/DoraTeam_iBot)"

__MODULE__ = "HHTươngTác"

# Lệnh -> category nekos.best (GIF), emoji custom (E_*), text tiếng Việt (caption: doer + text + target)
COMMANDS = {
    "punch": {"category": "punch", "emoji": E_FIRE, "text": "đã đấm"},
    "slap": {"category": "slap", "emoji": E_SIDEWAYS, "text": "đã tát"},
    "lick": {"category": "nom", "emoji": E_BITE_YOUR_LIPS, "text": "đã liếm"},
    "kill": {"category": "kick", "emoji": E_FIRE, "text": "đã giết"},
    "hug": {"category": "hug", "emoji": E_HEART2, "text": "đã ôm"},
    "bite": {"category": "bite", "emoji": E_BITE_YOUR_LIPS, "text": "đã cắn"},
    "kiss": {"category": "kiss", "emoji": E_HEART4, "text": "đã hôn"},
    "highfive": {"category": "highfive", "emoji": E_PARTY, "text": "đã đập tay"},
    "die": {"category": "cry", "emoji": E_CRY, "text": "đã chết"},
    "chay": {"category": "run", "emoji": E_ROCKET, "text": "đã chạy"},
    "shoot": {"category": "shoot", "emoji": E_FIRE, "text": "đã bắn"},
    "dance": {"category": "dance", "emoji": E_PARTY, "text": "đã nhảy"},
    "angry": {"category": "angry", "emoji": E_GLARE, "text": "đang giận"},
    "baka": {"category": "baka", "emoji": E_VUAM, "text": "đã baka"},
    "blush": {"category": "blush", "emoji": E_HEART4, "text": "đã đỏ mặt"},
    "bonk": {"category": "bonk", "emoji": E_WRENCH, "text": "đã bonk"},
    "bored": {"category": "bored", "emoji": E_TYMMY, "text": "đang chán"},
    "cry": {"category": "cry", "emoji": E_CRY, "text": "đã khóc"},
    "cuddle": {"category": "cuddle", "emoji": E_PENDING, "text": "đã ôm ấp"},
    "facepalm": {"category": "facepalm", "emoji": E_GLARE, "text": "đã facepalm"},
    "feed": {"category": "feed", "emoji": E_SWEET, "text": "đã cho ăn"},
    "handhold": {"category": "handhold", "emoji": E_HEART, "text": "đã nắm tay"},
    "handshake": {"category": "handshake", "emoji": E_HEART, "text": "đã bắt tay"},
    "happy": {"category": "happy", "emoji": E_EYE_ROLL, "text": "đang vui"},
    "kick": {"category": "kick", "emoji": E_FIRE, "text": "đã đá"},
    "laugh": {"category": "laugh", "emoji": E_VUAM, "text": "đã cười"},
    "lurk": {"category": "lurk", "emoji": E_VIEW, "text": "đã lén"},
    "nod": {"category": "nod", "emoji": E_EYE_ROLL, "text": "đã gật đầu"},
    "nom": {"category": "nom", "emoji": E_SWEET, "text": "đã nom"},
    "nope": {"category": "nope", "emoji": E_GLARE, "text": "đã lắc đầu"},
    "pat": {"category": "pat", "emoji": E_HEART, "text": "đã vỗ"},
    "peck": {"category": "peck", "emoji": E_HEART4, "text": "đã hôn nhẹ"},
    "poke": {"category": "poke", "emoji": E_TIP, "text": "đã chọc"},
    "pout": {"category": "pout", "emoji": E_SHOUT, "text": "đang phụng phịu"},
    "shrug": {"category": "shrug", "emoji": E_TYMMY, "text": "đã nhún vai"},
    "sleep": {"category": "sleep", "emoji": E_WAIT, "text": "đã ngủ"},
    "smile": {"category": "smile", "emoji": E_EYE_ROLL, "text": "đã cười"},
    "smug": {"category": "smug", "emoji": E_GLARE, "text": "đã đắc ý"},
    "stare": {"category": "stare", "emoji": E_VIEW, "text": "đã nhìn chằm chằm"},
    "tableflip": {"category": "tableflip", "emoji": E_SHOUT, "text": "đã lật bàn"},
    "think": {"category": "think", "emoji": E_TIP, "text": "đang suy nghĩ"},
    "thumbsup": {"category": "thumbsup", "emoji": E_SUCCESS, "text": "đã giơ ngón cái"},
    "tickle": {"category": "tickle", "emoji": E_VUAM, "text": "đã cù"},
    "wave": {"category": "wave", "emoji": E_VIEW, "text": "đã vẫy tay"},
    "wink": {"category": "wink", "emoji": E_WINK, "text": "đã nháy mắt"},
    "yawn": {"category": "yawn", "emoji": E_WAIT, "text": "đã ngáp"},
    "yeet": {"category": "yeet", "emoji": E_ROCKET, "text": "đã yeet"},
}

__HELP__ = (
    "<blockquote>GIF tương tác (nekos.best): "
    + ", ".join("/" + c for c in sorted(COMMANDS.keys()))
    + ". Reply tin người khác hoặc gửi không reply.</blockquote>"
)


def _fetch_nekos_url(category: str) -> str | None:
    """Gọi nekos.best API (chạy trong thread để không block)."""
    try:
        r = requests.get(
            f"{NEKOS_BEST_BASE}/{category}",
            headers={"User-Agent": NEKOS_UA},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if results and isinstance(results[0].get("url"), str):
            return results[0]["url"]
        return None
    except requests.exceptions.RequestException as e:
        LOGGER.warning("nekos.best fetch %s: %s", category, e)
        return None
    except (KeyError, IndexError, TypeError) as e:
        LOGGER.warning("nekos.best parse %s: %s", category, e)
        return None


async def get_animation(command: str) -> str | None:
    """Lấy URL GIF từ nekos.best cho lệnh đã cho."""
    info = COMMANDS.get(command.lower())
    if not info:
        return None
    category = info["category"]
    return await asyncio.to_thread(_fetch_nekos_url, category)


async def _send_feedback(chat_id: int, reply_to_id: int, text: str, msg=None):
    """Gửi phản hồi cho user: sửa tin đã gửi hoặc gửi tin mới nếu msg=None."""
    if msg:
        try:
            await msg.edit_text(text, parse_mode=enums.ParseMode.HTML)
            return
        except Exception:
            pass
    try:
        await app.send_message(
            chat_id, text, reply_to_message_id=reply_to_id, parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        LOGGER.warning("waifus _send_feedback: %s", e)


@app.on_message(
    filters.command(list(COMMANDS.keys()), COMMAND_HANDLER)
    & ~filters.forwarded
    & ~filters.via_bot,
    group=-1,
)
@capture_err
async def animation_command(_, ctx: Message):
    chat_id = ctx.chat.id
    reply_to_id = ctx.id
    cmd_name = (ctx.command or ["?"])[0].lower() if ctx.command else "?"
    LOGGER.info("waifus triggered command=%s chat_id=%s", cmd_name, chat_id)

    try:
        msg = await app.send_message(
            chat_id,
            f"{E_LOADING} Đang xử lý ảnh động...",
            reply_to_message_id=reply_to_id,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        LOGGER.warning("waifus send_message loading: %s", e)
        msg = None

    try:
        if not ctx.from_user:
            await _send_feedback(
                chat_id, reply_to_id, f"{E_ERROR} Lệnh này chỉ dành cho người dùng.", msg
            )
            return

        sender = ctx.from_user.mention(style="html")
        command = ctx.command[0].lower() if ctx.command else ""

        target = sender
        doer = sender
        if getattr(ctx, "reply_to_message", None):
            try:
                reply_msg = ctx.reply_to_message
                # doer = người gửi lệnh (sender), target = người được reply
                if getattr(reply_msg, "from_user", None) and reply_msg.from_user:
                    u = reply_msg.from_user
                    name = ((u.first_name or "") + (" " + (u.last_name or "") if u.last_name else "")).strip() or (u.username or "User")
                    target = f'<a href="tg://user?id={u.id}">{html.escape(name)}</a>'
                elif getattr(reply_msg, "sender_chat", None) and reply_msg.sender_chat:
                    target = html.escape(reply_msg.sender_chat.title or "User")
            except Exception as reply_err:
                LOGGER.warning("waifus reply target: %s", reply_err)

        gif_url = await get_animation(command)

        if gif_url:
            info = COMMANDS.get(command, {})
            caption = f"{doer} {info.get('text', '')} {target}! {info.get('emoji', '')}"
            try:
                await app.send_animation(
                    chat_id,
                    animation=gif_url,
                    caption=caption,
                    reply_to_message_id=reply_to_id,
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception as send_err:
                LOGGER.warning("waifus send_animation: %s", send_err)
                await _send_feedback(
                    chat_id, reply_to_id, f"{E_ERROR} Gửi ảnh động thất bại. Thử lại sau.", msg
                )
                return
            if msg:
                try:
                    await msg.delete()
                except Exception:
                    pass
        else:
            await _send_feedback(
                chat_id,
                reply_to_id,
                f"{E_ERROR} Không thể lấy ảnh động từ nekos.best. Vui lòng thử lại sau!",
                msg,
            )
    except Exception as e:
        LOGGER.exception("waifus %s: %s", cmd_name, e)
        await _send_feedback(chat_id, reply_to_id, f"{E_ERROR} Lỗi, vui lòng thử lại sau!", msg)
