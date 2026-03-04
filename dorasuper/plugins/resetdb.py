# Plugin reset database - chỉ admin (SUDO) mới dùng được, không hiện trong /help
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message

from database import dbname
from database.ai_chat_log_db import clear_ai_chat_logs
from dorasuper import app
from dorasuper.emoji import E_ERROR, E_LOADING, E_SUCCESS
from dorasuper.vars import COMMAND_HANDLER, SUDO

LOGGER = getLogger("DoraSuper")

# Danh sách collection đã dùng trong project (để drop khi reset)
COLLECTION_NAMES = [
    "afk",
    "users",
    "ai_chat_logs",
    "cleanmode",
    "filters",
    "sangmata",
    "checkin",
    "checkin_config",
    "checkin_usage",
    "warn",
    "karma",
    "imdb",
    "greetings",
    "gban",
    "blacklistFilters",
    "funny",
    "report_links",
    "locale",
    "notes",
    "userlist",
    "groups",
    "member_history",
]


@app.on_message(filters.command("resetdb", COMMAND_HANDLER) & filters.user(SUDO))
async def reset_database(_: app, message: Message):
    """Xóa toàn bộ dữ liệu trong database. Chỉ SUDO."""
    try:
        status = await message.reply(f"{E_LOADING} Đang reset database...", parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        LOGGER.warning("resetdb reply failed: %s", e)
        return
    cleared = []
    failed = []
    try:
        for name in COLLECTION_NAMES:
            try:
                coll = dbname[name]
                result = await coll.delete_many({})
                if result.deleted_count > 0:
                    cleared.append(f"{name}({result.deleted_count})")
                else:
                    cleared.append(name)
            except Exception as e:
                failed.append((name, str(e)))
        text = f"{E_SUCCESS} <b>Đã reset database.</b>\n\n<b>Đã xóa dữ liệu:</b> " + (", ".join(cleared) if cleared else "(không có)")
        if failed:
            text += "\n\n<b>Bỏ qua:</b> " + ", ".join(f[0] for f in failed)
        await status.edit_text(text, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        LOGGER.exception("resetdb error")
        try:
            await status.edit_text(f"{E_ERROR} Lỗi khi reset database:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)
        except Exception:
            await message.reply(f"{E_ERROR} Lỗi khi reset database:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)


@app.on_message(
    filters.command(["resetdb_ai", "resetdbai"], COMMAND_HANDLER) & filters.user(SUDO),
    group=-1,
)
async def reset_database_ai(_: app, message: Message):
    """Chỉ reset dữ liệu AI: log đối thoại (MongoDB) + lịch sử hội thoại trong memory."""
    try:
        status = await message.reply(
            f"{E_LOADING} Đang reset database AI...",
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        LOGGER.warning("resetdb_ai reply failed: %s", e)
        return
    try:
        from dorasuper.plugins.ai import clear_ai_chat_history

        deleted = await clear_ai_chat_logs()
        await clear_ai_chat_history()
        await status.edit_text(
            f"{E_SUCCESS} <b>Đã reset database AI.</b>\n\n"
            f"• Đã xóa <b>{deleted}</b> bản ghi log đối thoại (ai_chat_logs).\n"
            f"• Đã xóa lịch sử hội thoại trong memory.",
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        LOGGER.exception("resetdb_ai error")
        try:
            await status.edit_text(
                f"{E_ERROR} Lỗi khi reset database AI:\n<code>{e}</code>",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            await message.reply(f"{E_ERROR} Lỗi khi reset database AI:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)


@app.on_message(filters.command(["resetdb_ai", "resetdbai"], COMMAND_HANDLER), group=0)
async def resetdb_ai_no_permission(_: app, message: Message):
    """Trả lời khi user không phải SUDO gõ lệnh – để biết lệnh có chạy (trong nhóm cần /resetdb_ai@TênBot hoặc chat riêng)."""
    if message.from_user and message.from_user.id in SUDO:
        return
    await message.reply(
        f"{E_ERROR} Chỉ SUDO mới dùng được lệnh này.\n"
        "Trong nhóm: thử <code>/resetdb_ai@TênBot</code> hoặc gửi lệnh trong <b>chat riêng</b> với bot.",
        parse_mode=enums.ParseMode.HTML,
    )
