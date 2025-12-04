import logging
from logging import getLogger
from pyrogram.types import Message

from tiensiteo import app
from tiensiteo.helper.http import fetch
from tiensiteo.vars import CURRENCY_API

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "TiềnTệ"
__HELP__ = """
<blockquote>/doitien - Chuyển đổi và xem tỉ giá tiền tệ.</blockquote>
"""

def convert_number_to_text(number, currency):
    suffixes = [' tỉ', ' triệu', ' nghìn', '']
    number = float(number)
    parts = []

    for i, suffix in enumerate(suffixes):
        if number >= 1000 ** (len(suffixes) - i - 1):
            unit = 1000 ** (len(suffixes) - i - 1)
            value = int(number // unit)
            number %= unit
            if value > 0:
                parts.append(f"{value}{suffix}")

    return ", ".join(parts) + f" {currency}"

@app.on_cmd("doitien")
async def currency(_, ctx: Message):
    if CURRENCY_API is None:
        return await ctx.reply_msg(
            "<code>Oops!!get the API from</code> <a href='https://app.exchangerate-api.com/sign-up'>HERE</a> <code>& add it to config vars</code> (<code>CURRENCY_API</code>)",
            disable_web_page_preview=True,
        )
    if len(ctx.text.split()) != 4:
        return await ctx.reply_msg(
            f"Sử dụng cấu trúc /{ctx.command[0]} [số tiền] [loại tiền ban đầu] [loại tiền cần đổi] để chuyển đổi tiền tệ.",
            del_in=6,
        )

    _, amount, currency_from, currency_to = ctx.text.split()
    if amount.isdigit() or (
        amount.replace(".", "", 1).isdigit() and amount.count(".") < 2
    ):
        url = (
            f"https://v6.exchangerate-api.com/v6/{CURRENCY_API}/"
            f"pair/{currency_from}/{currency_to}/{amount}"
        )
        try:
            res = await fetch.get(url)
            data = res.json()
            try:
                conversion_rate = data["conversion_rate"]
                conversion_result = data["conversion_result"]
                target_code = data["target_code"]
                base_code = data["base_code"]
                last_update = data["time_last_update_utc"]
            except KeyError:
                return await ctx.reply_msg("<code>Chuyển đổi tiền tệ không thành công, có thể bạn cung cấp sai định dạng tiền tệ hoặc lỗi api!</i>")
            
            amount_text = convert_number_to_text(amount, base_code)
            conversion_result_text = convert_number_to_text(conversion_result, target_code)
            conversion_rate_text = convert_number_to_text(conversion_rate, target_code)

            await ctx.reply_msg(
                f"**KẾT QUẢ TỶ GIÁ HỐI ĐỔI TIỀN TỆ:**\n\n"
                f"`{format(float(amount), ',')}` **{base_code}** ({amount_text}) = "
                f"`{format(float(conversion_result), ',')}` **{target_code}** ({conversion_result_text})\n"
                f"<b>Rate Hôm nay:</b> `{format(float(conversion_rate), ',')}` ({conversion_rate_text})\n"
                f"<b>Cập nhật cuối:</b> {last_update}"
            )
        except Exception as err:
            await ctx.reply_msg(
                f"Chuyển đổi tiền tệ không thành công, có thể bạn cung cấp sai định dạng tiền tệ hoặc lỗi api.\n\n<b>LỖI</b>: {err}"
            )
    else:
        await ctx.reply_msg(
            "<code>Đây có vẻ là một loại tiền tệ của người ngoài hành tinh mà tôi không thể chuyển đổi ngay bây giờ.. (⊙_⊙;)</code>"
        )