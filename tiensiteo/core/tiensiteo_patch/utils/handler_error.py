# tgEasy - Easy for a brighter Shine. A monkey pather add-on for Pyrogram
# Copyright (C) 2021 - 2022 Jayant Hegde Kageri <https://github.com/jayantkageri>

# This file is part of tgEasy.

# tgEasy is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# tgEasy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with tgEasy.  If not, see <http://www.gnu.org/licenses/>.
import contextlib
import logging
import os
import traceback
import typing
from datetime import datetime

import pyrogram

from tiensiteo.vars import LOG_CHANNEL

LOGGER = logging.getLogger("TienSiTeo")


async def handle_error(
    _, m: typing.Union[pyrogram.types.Message, pyrogram.types.CallbackQuery]
):
    """
    ### `handle_error`
    - A Function to Handle the Errors in Functions.
    - This Sends the Error Log to the Log Group and Replies Sorry Message for the Users.
    - This is Helper for all of the functions for handling the Errors.

    - Parameters:
      - error:
        - The Exceptation.

      - m (`pyrogram.types.Message` or `pyrogram.types.CallbackQuery`):
        - The Message or Callback Query where the Error occurred.

    """

    day = datetime.now()
    tgl_now = datetime.now()
    cap_day = f"{day.strftime('%A')}, {tgl_now.strftime('%d %B %Y %H:%M:%S')}"
    f_errname = f"crash_{tgl_now.strftime('%d %B %Y')}.txt"
    LOGGER.error(traceback.format_exc())
    with open(f_errname, "w+", encoding="utf-8") as log:
        log.write(
            f"✍️ Message: {m.text or m.caption}\n👱‍♂️ User: {m.from_user.id if m.from_user else m.sender_chat.id}\n\n{traceback.format_exc()}"
        )
        log.close()
    if isinstance(m, pyrogram.types.Message):
        with contextlib.suppress(Exception):
            try:
                await m.reply_photo(
                    "https://api.dabeecao.org/deo_thanh_cong.jpg",
                    caption="Đã xảy ra lỗi nội bộ trong khi xử lý lệnh của bạn, Nhật ký đã được gửi đến @dabeecao. Xin lỗi vì sự bất tiện",
                )
            except:
                await m.reply_msg(
                    "Đã xảy ra lỗi nội bộ trong khi xử lý lệnh của bạn, Nhật ký đã được gửi đến @dabeecao. Xin lỗi vì sự bất tiện"
                )
            await m._client.send_document(
                LOG_CHANNEL,
                f_errname,
                caption=f"Báo cáo sự cố của Bot này\n{cap_day}",
            )
    if isinstance(m, pyrogram.types.CallbackQuery):
        with contextlib.suppress(Exception):
            await m.message.delete()
            try:
                await m.reply_photo(
                    "https://api.dabeecao.org/deo_thanh_cong.jpg",
                    caption="Đã xảy ra lỗi nội bộ trong khi xử lý lệnh của bạn, Nhật ký đã được gửi đến @dabeecao. Xin lỗi vì sự bất tiện",
                )
            except:
                await m.message.reply_msg(
                    "Đã xảy ra lỗi nội bộ trong khi xử lý lệnh của bạn, Nhật ký đã được gửi đến @dabeecao. Xin lỗi vì sự bất tiện"
                )
            await m.message._client.send_document(
                LOG_CHANNEL,
                f_errname,
                caption=f"Báo cáo sự cố của Bot này\n{cap_day}",
            )
    if os.path.exists(f_errname):
        os.remove(f_errname)
    return True
