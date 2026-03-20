import os
import traceback
from datetime import datetime
from functools import wraps

from pyrogram.enums import ParseMode
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden
from pyrogram.types import CallbackQuery

from dorasuper.emoji import E_ADMIN, E_ERROR
from dorasuper.vars import LOG_CHANNEL
from dorasuper.log_topics import LOG_TOPIC_IDS


def capture_err(func):
    @wraps(func)
    async def capture(client, message, *args, **kwargs):
        if isinstance(message, CallbackQuery):
            sender = message.message.reply
            chat = message.message.chat
            msg = message.message.text or message.message.caption
        else:
            sender = message.reply
            chat = message.chat
            msg = message.text or message.caption
        try:
            return await func(client, message, *args, **kwargs)
        except ChatWriteForbidden:
            return await client.leave_chat(message.chat.id)
        except Exception as err:
            exc = traceback.format_exc()
            error_feedback = "ERROR | {} | {}\n\n{}\n\n{}\n".format(
                message.from_user.id if message.from_user else 0,
                chat.id if chat else 0,
                msg,
                exc,
            )
            day = datetime.now()
            tgl_now = datetime.now()

            cap_day = f"{day.strftime('%A')}, {tgl_now.strftime('%d %B %Y %H:%M:%S')}"
            await sender(
                f"{E_ERROR} Đã xảy ra lỗi nội bộ trong khi xử lý Lệnh của bạn, Nhật ký đã được gửi đến @ThanhDora{E_ADMIN}. Xin lỗi vì sự bất tiện này...",
                parse_mode=ParseMode.HTML,
            )
            with open(
                f"crash_{tgl_now.strftime('%d %B %Y')}.txt", "w+", encoding="utf-8"
            ) as log:
                log.write(error_feedback)
                log.close()
            await client.send_document(
                LOG_CHANNEL,
                f"crash_{tgl_now.strftime('%d %B %Y')}.txt",
                caption=f"{E_ERROR} Báo cáo sự cố của Bot này\n{cap_day}",
                parse_mode=ParseMode.HTML,
                message_thread_id=LOG_TOPIC_IDS["errors"],
            )
            os.remove(f"crash_{tgl_now.strftime('%d %B %Y')}.txt")
            raise err

    return capture
