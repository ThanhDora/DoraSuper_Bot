import random
from html import escape
from logging import getLogger
from pyrogram import enums, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dorasuper import app
from dorasuper.emoji import (
    E_ERROR,
    E_FIRE,
    E_FLOWER,
    E_HEART2,
    E_LIMIT,
    E_LOADING,
    E_RAINBOW,
    E_SPARKLE,
    E_USER,
    E_WARN,
)
from dorasuper.core.decorator.errors import capture_err
from dorasuper.vars import COMMAND_HANDLER
from dorasuper.helper.safe_reply import reply_safe

LOGGER = getLogger("DoraSuper")

try:
    from database.funny_db import can_use_command, update_user_command_usage
except Exception as e:
    LOGGER.warning("funny_rate: không load được funny_db, bỏ qua giới hạn: %s", e)
    can_use_command = None
    update_user_command_usage = None

__MODULE__ = "ĐánhGiáVui"
__HELP__ = """
<blockquote>/cutie - Đánh giá mức độ dễ thương của bạn hoặc người được trả lời.
/hot - Đánh giá mức độ nóng bỏng của bạn hoặc người được trả lời.
/horny - Đánh giá mức độ... tò mò của bạn hoặc người được trả lời.
/sexy - Đánh giá mức độ quyến rũ của bạn hoặc người được trả lời.
/gay - Đánh giá mức độ gay của bạn hoặc người được trả lời.
/lesbian - Đánh giá mức độ lesbian của bạn hoặc người được trả lời.
/boob - Đánh giá kích thước... của bạn hoặc người được trả lời.
/cock - Đánh giá kích thước... của bạn hoặc người được trả lời.</blockquote>
"""

# Định nghĩa các link media
MEDIA = {
    "cutie": "https://graph.org/file/24375c6e54609c0e4621c.mp4",
    "hot": "https://graph.org/file/745ba3ff07c1270958588.mp4",
    "horny": "https://graph.org/file/eaa834a1cbfad29bd1fe4.mp4",
    "sexy": "https://graph.org/file/58da22eb737af2f8963e6.mp4",
    "gay": "https://graph.org/file/850290f1f974c5421ce54.mp4",
    "lesbian": "https://graph.org/file/ff258085cf31f5385db8a.mp4",
    "boob": "https://i.gifer.com/8ZUg.gif",
    "cock": "https://telegra.ph/file/423414459345bf18310f5.gif"
}

# Nút hỗ trợ
BUTTON = [[InlineKeyboardButton("Ủng Hộ", url="https://thanhdora3605.dev")]]

# Hàm chung để xử lý các lệnh
async def handle_fun_command(ctx, command, caption_template, emoji):
    msg = None
    try:
        # Phản hồi ngay (dùng app.send_message để tránh lỗi bound/patch)
        loading_text = f"{E_LOADING} Đang xử lý..."
        try:
            msg = await app.send_message(
                ctx.chat.id,
                loading_text,
                reply_to_message_id=ctx.id,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as e1:
            LOGGER.warning("funny_rate send_message: %s", e1)
            try:
                msg = await reply_safe(ctx, loading_text, quote=True)
            except Exception:
                msg = await app.send_message(ctx.chat.id, "⏳ Đang xử lý...", reply_to_message_id=ctx.id)
        if not msg:
            return

        sender = getattr(ctx, "from_user", None)
        if not sender:
            try:
                await msg.edit_text(f"{E_USER} Chỉ dùng lệnh này từ tài khoản thành viên.", parse_mode=enums.ParseMode.HTML)
            except Exception:
                await reply_safe(ctx, f"{E_USER} Chỉ dùng lệnh này từ tài khoản thành viên.", quote=True)
            return

        chat_id = ctx.chat.id
        sender_id = sender.id

        if ctx.reply_to_message:
            target = getattr(ctx.reply_to_message, "from_user", None)
            if not target:
                try:
                    await msg.edit_text(f"{E_WARN} Không xác định được người được trả lời.", parse_mode=enums.ParseMode.HTML)
                except Exception:
                    await reply_safe(ctx, f"{E_WARN} Không xác định được người được trả lời.", quote=True)
                return
            user_id = target.id
            user_name = getattr(target, "first_name", None) or "User"
        else:
            user_id = sender.id
            user_name = getattr(sender, "first_name", None) or "User"

        # Giới hạn 1 lần/ngày (bỏ qua nếu DB không load)
        if can_use_command is not None:
            try:
                if not await can_use_command(chat_id, sender_id, command):
                    await reply_safe(
                        ctx,
                        f"{E_LIMIT} Bạn đã dùng /{command} hôm nay. Thử lại ngày mai!",
                        quote=True,
                        parse_mode=enums.ParseMode.HTML,
                    )
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                    return
            except Exception as db_err:
                LOGGER.warning("funny_rate can_use_command: %s", db_err)

        mention = f'<a href="tg://user?id={user_id}">{escape(user_name)}</a>'
        percentage = random.randint(1, 100)
        caption = caption_template.format(mention=mention, value=percentage)

        try:
            await app.send_document(
                chat_id=ctx.chat.id,
                document=MEDIA[command],
                caption=caption,
                parse_mode=enums.ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(BUTTON),
                reply_to_message_id=ctx.reply_to_message.id if ctx.reply_to_message else ctx.id,
            )
        except Exception as send_err:
            LOGGER.warning("funny_rate send_document %s: %s", command, send_err)
            err_text = f"{E_ERROR} Lỗi gửi media: {send_err!s}. Thử lại sau."
            try:
                await msg.edit_text(err_text, parse_mode=enums.ParseMode.HTML)
            except Exception:
                await reply_safe(ctx, err_text, quote=True)
            return

        try:
            await msg.delete()
        except Exception:
            pass

        if update_user_command_usage is not None:
            try:
                await update_user_command_usage(chat_id, sender_id, command)
            except Exception as db_err:
                LOGGER.warning("funny_rate update_user_command_usage: %s", db_err)

    except Exception as e:
        LOGGER.warning("funny_rate %s: %s", command, e, exc_info=True)
        fallback = f"{E_ERROR} Lỗi, vui lòng thử lại sau."
        try:
            await reply_safe(ctx, fallback, quote=True)
        except Exception:
            try:
                await ctx.reply_text("Lỗi, vui lòng thử lại sau.", quote=True)
            except Exception:
                if msg:
                    try:
                        await msg.edit_text("Lỗi, vui lòng thử lại sau.")
                    except Exception:
                        pass

# group=-1: chạy sớm như /start, /help, /ping để tránh handler khác chặn
_FUNNY_FILTER = filters.command(
    ["cutie", "hot", "horny", "sexy", "gay", "lesbian", "boob", "cock"],
    COMMAND_HANDLER,
)

@app.on_message(_FUNNY_FILTER, group=-1)
@capture_err
async def funny_rate_handler(_, ctx):
    cmd = (ctx.command or [None])[0]
    if not cmd:
        return
    templates = {
        "cutie": (f"{E_SPARKLE} {{mention}} dễ thương {{value}}% nhé! {E_FLOWER}{E_HEART2}", "cutie"),
        "hot": (f"{E_FIRE} {{mention}} nóng bỏng {{value}}%! {E_FIRE}", "hot"),
        "horny": (f"{E_FIRE} {{mention}} tò mò {{value}}% nha! {E_FIRE}", "horny"),
        "sexy": (f"{E_FIRE} {{mention}} quyến rũ {{value}}%! {E_FIRE}", "sexy"),
        "gay": (f"{E_RAINBOW} {{mention}} gay {{value}}% nè! {E_RAINBOW}", "gay"),
        "lesbian": (f"{E_FLOWER}{E_HEART2} {{mention}} lesbian {{value}}% đó! {E_RAINBOW}", "lesbian"),
        "boob": (f"🍒 Kích thước ngực của {{mention}} là {{value}}! {E_SPARKLE}", "boob"),
        "cock": (f"🍆 Kích thước của {{mention}} là {{value}}cm! {E_FIRE}", "cock"),
    }
    spec = templates.get(cmd.lower())
    if spec:
        await handle_fun_command(ctx, cmd.lower(), spec[0], spec[1])