# Plugin reset database - chỉ admin (SUDO) mới dùng được, không hiện trong /help
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.types import Message

from database import dbname
from dorasuper import app
from dorasuper.emoji import E_ERROR, E_LOADING, E_SUCCESS
from dorasuper.vars import COMMAND_HANDLER, SUDO

LOGGER = getLogger("DoraSuper")

# Danh sách collection đã dùng trong project (để drop khi reset)
COLLECTION_NAMES = [
    "users",
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
    status = await message.reply_msg(f"{E_LOADING} Đang reset database...", parse_mode=enums.ParseMode.HTML)
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
        await status.edit_msg(text, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        LOGGER.exception("resetdb error")
        await status.edit_msg(f"{E_ERROR} Lỗi khi reset database:\n<code>{e}</code>", parse_mode=enums.ParseMode.HTML)
