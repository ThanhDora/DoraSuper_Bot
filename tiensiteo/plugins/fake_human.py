import requests
import logging
from logging import getLogger
from pyrogram import filters
from pyrogram.types import Message
from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.vars import COMMAND_HANDLER

VALID_COUNTRY_CODES = [
    "AU", "BR", "CA", "CH", "DE", "DK", "ES", "FI", "FR", "GB",
    "IE", "IR", "NO", "NL", "NZ", "TR", "US"
]

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "TạoĐịaChỉGiả"
__HELP__ = "<blockquote>/fake [mã quốc gia] - Tạo địa chỉ giả dựa trên mã quốc gia.</blockquote>"

@app.on_message(filters.command(["fake"], COMMAND_HANDLER))
@capture_err
async def address(_, ctx: Message):
    # Phản hồi ngay lập tức khi nhận lệnh
    msg = await ctx.reply_msg("Đang xử lý tạo địa chỉ giả, vui lòng đợi...", quote=True)

    try:
        query = ctx.text.split(None, 1)[1].strip().upper()
    except IndexError:
        await msg.edit_msg("Vui lòng cung cấp mã quốc gia!")
        return

    if query not in VALID_COUNTRY_CODES:
        await msg.edit_msg(f"Mã quốc gia không hợp lệ. Vui lòng sử dụng một trong các mã sau: {', '.join(VALID_COUNTRY_CODES)}")
        return

    try:
        url = f"https://randomuser.me/api/?nat={query}"
        response = requests.get(url)

        if response.status_code != 200:
            raise Exception("Không thể lấy dữ liệu từ API.")

        data = response.json()

        if "results" not in data:
            raise Exception("Không tìm thấy thông tin địa chỉ.")

        user_data = data["results"][0]

        name = f"{user_data['name']['title']} {user_data['name']['first']} {user_data['name']['last']}"
        address = f"{user_data['location']['street']['number']} {user_data['location']['street']['name']}"
        city = user_data['location']['city']
        state = user_data['location']['state']
        country = user_data['location']['country']
        postal = user_data['location']['postcode']
        email = user_data['email']
        phone = user_data['phone']
        picture_url = user_data['picture']['large']

        caption = f"""
**Tên**: {name}
**Địa chỉ**: {address}
**Quốc gia**: {country}
**Thành phố**: {city}
**Bang**: {state}
**Mã bưu điện**: {postal}
**Email**: {email}
**Số điện thoại**: {phone}
"""

        await ctx.reply_photo(
            photo=picture_url,
            caption=caption,
            reply_to_message_id=ctx.id
        )
    except Exception as e:
        await msg.edit_msg(f"Lỗi: {str(e)}")
    finally:
        await msg.delete()