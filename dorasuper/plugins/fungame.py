import asyncio
import logging
from logging import getLogger

from pyrogram import Client, enums
from pyrogram.types import Message

from dorasuper import app
from dorasuper.core.decorator import new_task

LOGGER = getLogger("DoraSuper")
LOGGER. setLevel(logging.INFO)

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

@app.on_cmd("dice")
@new_task
async def dice(self: Client, ctx: Message):
    try:
        x = await self.send_dice(ctx.chat.id, reply_to_message_id=ctx.id)
        m = x.dice.value
        await ctx.reply_msg(
            f"Xin chào {ctx.from_user.mention if ctx.from_user else ctx.sender_chat.title}, điểm của bạn là: {m}",
            quote=True
        )
    except Exception as e:
        LOGGER.error(f"Error in /dice: {str(e)}")
        await ctx.reply_msg(f"Lỗi: {str(e)}", quote=True)

@app.on_cmd("dart")
@new_task
async def dart(self: Client, ctx: Message):
    try:
        x = await self.send_dice(ctx.chat.id, "🎯", reply_to_message_id=ctx.id)
        m = x.dice.value
        await ctx.reply_msg(
            f"Xin chào {ctx.from_user.mention if ctx.from_user else ctx.sender_chat.title}, điểm của bạn là: {m}",
            quote=True
        )
    except Exception as e:
        LOGGER.error(f"Error in /dart: {str(e)}")
        await ctx.reply_msg(f"Lỗi: {str(e)}", quote=True)

@app.on_cmd("basket")
@new_task
async def basket(self: Client, ctx: Message):
    try:
        x = await self.send_dice(ctx.chat.id, "🏀", reply_to_message_id=ctx.id)
        m = x.dice.value
        await ctx.reply_msg(
            f"Xin chào {ctx.from_user.mention if ctx.from_user else ctx.sender_chat.title}, điểm của bạn là: {m}",
            quote=True
        )
    except Exception as e:
        LOGGER.error(f"Error in /basket: {str(e)}")
        await ctx.reply_msg(f"Lỗi: {str(e)}", quote=True)

@app.on_cmd("jackpot")
@new_task
async def jackpot(self: Client, ctx: Message):
    try:
        x = await self.send_dice(ctx.chat.id, "🎰", reply_to_message_id=ctx.id)
        m = x.dice.value
        await ctx.reply_msg(
            f"Xin chào {ctx.from_user.mention if ctx.from_user else ctx.sender_chat.title}, điểm của bạn là: {m}",
            quote=True
        )
    except Exception as e:
        LOGGER.error(f"Error in /jackpot: {str(e)}")
        await ctx.reply_msg(f"Lỗi: {str(e)}", quote=True)

@app.on_cmd("ball")
@new_task
async def ball(self: Client, ctx: Message):
    try:
        x = await self.send_dice(ctx.chat.id, "🎳", reply_to_message_id=ctx.id)
        m = x.dice.value
        await ctx.reply_msg(
            f"Xin chào {ctx.from_user.mention if ctx.from_user else ctx.sender_chat.title}, điểm của bạn là: {m}",
            quote=True
        )
    except Exception as e:
        LOGGER.error(f"Error in /ball: {str(e)}")
        await ctx.reply_msg(f"Lỗi: {str(e)}", quote=True)

@app.on_cmd("football")
@new_task
async def football(self: Client, ctx: Message):
    try:
        x = await self.send_dice(ctx.chat.id, "⚽", reply_to_message_id=ctx.id)
        m = x.dice.value
        await ctx.reply_msg(
            f"Xin chào {ctx.from_user.mention if ctx.from_user else ctx.sender_chat.title}, điểm của bạn là: {m}",
            quote=True
        )
    except Exception as e:
        LOGGER.error(f"Error in /football: {str(e)}")
        await ctx.reply_msg(f"Lỗi: {str(e)}", quote=True)