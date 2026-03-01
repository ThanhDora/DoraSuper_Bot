import requests
import json
import re
import asyncio
import logging
from logging import getLogger
from pyrogram import enums, filters
from dorasuper import app
from dorasuper.emoji import E_CHECK, E_CROSS
from dorasuper.core.decorator.errors import capture_err
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")

__MODULE__ = "KTSốĐT"
__HELP__ = "<blockquote>/ktsdt [số điện thoại] - Kiểm tra thông tin số điện thoại. Số phải bắt đầu bằng mã vùng (ví dụ: +1, +84, +44...).</blockquote>"

@app.on_message(filters.command(["ktsdt"], COMMAND_HANDLER))
@capture_err
async def check_phone(_, ctx):
    msg = await ctx.reply_msg("Đang kiểm tra số điện thoại, vui lòng đợi...", quote=True)
    try:
        args = ctx.text.split(None, 1)
        if len(args) < 2:
            raise ValueError("Vui lòng cung cấp số điện thoại!")

        number = args[1].strip()
        # Kiểm tra định dạng số điện thoại (phải bắt đầu bằng + và mã vùng 1-3 chữ số)
        if not re.match(r"^\+\d{1,3}\d+$", number):
            raise ValueError("Số điện thoại phải bắt đầu bằng mã vùng hợp lệ (ví dụ: +1, +84, +44...). Vui lòng nhập lại!")

        key = ""
        api = f"http://apilayer.net/api/validate?access_key={key}&number={number}&country_code=&format=1"
        
        output = requests.get(api)
        output.raise_for_status()  # Kiểm tra lỗi HTTP
        obj = json.loads(output.text)
        
        # Lấy thông tin từ API
        valid = obj.get("valid", False)
        country_code = obj.get("country_code")
        country_name = obj.get("country_name")
        location = obj.get("location")
        carrier = obj.get("carrier")
        line_type = obj.get("line_type")
        
        # Tạo thông điệp kết quả, chỉ thêm dòng nếu giá trị không None hoặc rỗng
        result = ["<b>Kết quả kiểm tra số điện thoại</b>:"]
        result.append(f"📞 Số điện thoại: {number}")
        result.append(f"Số có tồn tại: {f'{E_CHECK} Có' if valid else f'{E_CROSS} Không'}")
        
        if country_code:
            result.append(f"🌍 Mã quốc gia: {country_code}")
        if country_name:
            result.append(f"🏳️ Tên quốc gia: {country_name}")
        if location:
            result.append(f"📍 Vị trí: {location}")
        if carrier:
            result.append(f"📡 Nhà mạng: {carrier}")
        if line_type:
            result.append(f"📱 Loại thiết bị: {line_type}")
        
        # Gộp các dòng thành chuỗi
        final_result = "\n".join(result)
        
        await ctx.reply_msg(final_result, quote=True, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        await msg.edit_msg(f"Lỗi: {str(e)}")
        await asyncio.sleep(5)  # Chờ 5 giây trước khi xóa thông báo lỗi
    finally:
        await msg.delete()