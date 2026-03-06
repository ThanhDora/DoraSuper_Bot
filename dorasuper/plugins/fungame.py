import logging
from logging import getLogger

from pyrogram import Client, enums, filters
from pyrogram.types import Message

from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.emoji import E_DART, E_ERROR, E_PARTY, E_TROPHY
from dorasuper.helper.safe_reply import reply_safe
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")
LOGGER.setLevel(logging.INFO)

__MODULE__ = "TròChơi"
__HELP__ = """
<blockquote>Chơi trò chơi với các biểu tượng cảm xúc:
/dice - Xúc xắc 🎲
/tungxu - Đồng xu 🪙
/dart - Phi tiêu 🎯
/basket - Bóng rổ 🏀
/ball - Bóng bowling 🎳
/football - Bóng đá ⚽
/jackpot - Máy đánh bạc 🎰</blockquote>
"""

# dice: None = mặc định 🎲; các lệnh khác: emoji truyền vào send_dice
GAME_EMOJI = {
    "dice": None,
    "dart": "🎯",
    "basket": "🏀",
    "jackpot": "🎰",
    "ball": "🎳",
    "football": "⚽",
}

# Prefix tin điểm theo từng game (emoji + "Xin chào ...")
SCORE_PREFIX = {
    "dice": f"{E_PARTY}",
    "dart": f"{E_DART}",
    "basket": "🏀",
    "jackpot": "🎰",
    "ball": "🎳",
    "football": "⚽",
}


def _mention(ctx: Message):
    if getattr(ctx, "from_user", None):
        return ctx.from_user.mention
    return getattr(getattr(ctx, "sender_chat", None), "title", "Bạn")


async def _reply_score(ctx: Message, text: str, score: int = None):
    try:
        await reply_safe(ctx, text, quote=True, parse_mode=enums.ParseMode.HTML)
    except Exception:
        try:
            msg = f"Điểm của bạn: {score}" if score is not None else "Đã gửi."
            await ctx.reply_text(msg, quote=True)
        except Exception:
            pass


# group=-1: chạy sớm, tránh on_cmd/cooldown hoặc handler khác chặn
@app.on_message(
    filters.command(
        ["dice", "dart", "basket", "jackpot", "ball", "football"],
        COMMAND_HANDLER,
    ),
    group=-1,
)
@capture_err
async def fungame_handler(_: Client, ctx: Message):
    cmd = (ctx.command or [None])[0]
    if not cmd:
        return
    cmd = cmd.lower()
    if cmd not in GAME_EMOJI:
        return
    try:
        emoji = GAME_EMOJI[cmd]
        if emoji is None:
            x = await app.send_dice(ctx.chat.id, reply_to_message_id=ctx.id)
        else:
            x = await app.send_dice(ctx.chat.id, emoji, reply_to_message_id=ctx.id)
        m = x.dice.value
        prefix = SCORE_PREFIX.get(cmd, E_TROPHY)
        text = f"{prefix} Xin chào {_mention(ctx)}, {E_TROPHY} điểm của bạn là: {m}"
        await _reply_score(ctx, text, m)
    except Exception as e:
        LOGGER.warning("fungame %s: %s", cmd, e, exc_info=True)
        try:
            await reply_safe(ctx, f"{E_ERROR} Lỗi: {str(e)}", quote=True, parse_mode=enums.ParseMode.HTML)
        except Exception:
            try:
                await ctx.reply_text(f"Lỗi: {str(e)}", quote=True)
            except Exception:
                pass
