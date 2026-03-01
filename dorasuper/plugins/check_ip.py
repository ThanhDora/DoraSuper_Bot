import requests
import dns.resolver
import asyncio
import logging
from logging import getLogger

from pyrogram import enums, filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from dorasuper import app
from dorasuper.emoji import E_CHECK, E_CROSS, E_ERROR, E_GLOBE, E_LOADING, E_PIN, E_PIN_LOC, E_WARN
from dorasuper.core.decorator.errors import capture_err
from dorasuper.vars import COMMAND_HANDLER
from urllib.parse import urlparse

LOGGER = getLogger("DoraSuper")

IPINFO_TOKEN = ''
IPQUALITYSCORE_API_KEY = ''

__MODULE__ = "KiểmTraIP"
__HELP__ = "<blockquote>/checkip [địa chỉ IP hoặc tên miền] - Kiểm tra thông tin và điểm chất lượng của địa chỉ IP hoặc tên miền. Ví dụ: /checkip 8.8.8.8 hoặc /checkip google.com</blockquote>"

@app.on_message(filters.command(["checkip"], COMMAND_HANDLER))
@capture_err
async def ip_info_and_score(_, ctx: Message):
    msg = await ctx.reply_msg(f"{E_LOADING} Đang xử lý kiểm tra, vui lòng đợi.", quote=True, parse_mode=enums.ParseMode.HTML)

    try:
        if len(ctx.command) != 2:
            raise Exception(f"{E_ERROR} Vui lòng cung cấp địa chỉ IP hoặc tên miền sau lệnh. Ví dụ: /ip 8.8.8.8 hoặc /ip google.com")

        input_value = ctx.command[1]
        # Xử lý URL nếu có http:// hoặc https://
        if input_value.startswith(("http://", "https://")):
            parsed_url = urlparse(input_value)
            input_value = parsed_url.netloc or parsed_url.path.split("/")[0]

        ip_addresses = get_ip_from_input(input_value)

        if not ip_addresses:
            raise Exception(f"{E_ERROR} Không thể tìm thấy địa chỉ IP nào cho đầu vào cung cấp.")

        if len(ip_addresses) == 1:
            ip_info = get_ip_info(ip_addresses[0])
            ip_score, score_description, emoji = get_ip_score(ip_addresses[0], IPQUALITYSCORE_API_KEY)
            if ip_info and ip_score is not None:
                response_message = (
                    f"{ip_info}\n\n"
                    f"<b>Điểm IP</b>: {ip_score} {emoji} ({score_description})"
                )
                await ctx.reply_text(response_message, reply_to_message_id=ctx.id, parse_mode=enums.ParseMode.HTML)
            else:
                raise Exception(f"{E_ERROR} Không thể lấy thông tin cho địa chỉ IP cung cấp.")
        else:
            # Hiển thị các nút chọn IP
            buttons = [
                [InlineKeyboardButton(f"IP: {ip}", callback_data=f"ip_select_{ip}")]
                for ip in ip_addresses
            ]
            await ctx.reply_text(
                "Tên miền có nhiều địa chỉ IP. Vui lòng chọn một IP để kiểm tra:",
                reply_markup=InlineKeyboardMarkup(buttons),
                reply_to_message_id=ctx.id
            )
    except Exception as e:
        error_msg = await ctx.reply_text(f"{E_ERROR} Lỗi: {str(e)}", reply_to_message_id=ctx.id, parse_mode=enums.ParseMode.HTML)
        await asyncio.sleep(5)  # Đợi 5 giây
        await error_msg.delete()  # Xóa thông báo lỗi
    finally:
        await msg.delete()

@app.on_callback_query(filters.regex(r"ip_select_(.+)"))
async def ip_select_callback(client: Client, callback_query):
    ip_address = callback_query.data.split("_")[-1]
    await callback_query.message.edit_text(f"{E_LOADING} Đang kiểm tra IP đã chọn.", parse_mode=enums.ParseMode.HTML)
    ip_info = get_ip_info(ip_address)

    ip_score, score_description, emoji = get_ip_score(ip_address, IPQUALITYSCORE_API_KEY)

    if ip_info and ip_score is not None:
        response_message = (
            f"{ip_info}\n\n"
            f"<b>Điểm IP</b>: {ip_score} {emoji} ({score_description})"
        )
        await callback_query.message.edit_text(response_message, parse_mode=enums.ParseMode.HTML)
    else:
        error_msg = await callback_query.message.edit_text(f"{E_ERROR} Không thể lấy thông tin cho địa chỉ IP đã chọn.", parse_mode=enums.ParseMode.HTML)
        await asyncio.sleep(5)  # Đợi 5 giây
        await error_msg.delete()  # Xóa thông báo lỗi

def get_ip_from_input(input_value):
    """Kiểm tra nếu đầu vào là tên miền thì trả về danh sách IP, nếu là IP thì trả về danh sách chứa IP đó."""
    try:
        # Kiểm tra xem đầu vào có phải là địa chỉ IP hợp lệ
        parts = input_value.split(".")
        if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            return [input_value]

        # Nếu là tên miền, thực hiện tra cứu DNS
        answers = dns.resolver.resolve(input_value, "A")
        return [str(answer) for answer in answers]
    except Exception as e:
        LOGGER.warning("Lỗi khi tra cứu DNS: %s", e)
        return []

def get_ip_info(ip_address):
    api_url = f"https://ipinfo.io/{ip_address}?token={IPINFO_TOKEN}"
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            info = (
                f"{E_GLOBE} <b>IP</b>: {data.get('ip', 'N/A')}\n"
                f"<b>Thành phố</b>: {data.get('city', 'N/A')}\n"
                f"{E_PIN_LOC} <b>Khu vực</b>: {data.get('region', 'N/A')}\n"
                f"{E_GLOBE} <b>Quốc gia</b>: {data.get('country', 'N/A')}\n"
                f"{E_PIN} <b>Vị trí</b>: {data.get('loc', 'N/A')}\n"
                f"<b>Tổ chức</b>: {data.get('org', 'N/A')}\n"
                f"<b>Mã bưu điện</b>: {data.get('postal', 'N/A')}\n"
                f"<b>Múi giờ</b>: {data.get('timezone', 'N/A')}"
            )
            return info
        return None
    except Exception as e:
        LOGGER.warning("Lỗi khi lấy thông tin IP: %s", e)
        return None

def get_ip_score(ip_address, api_key):
    api_url = f"https://ipqualityscore.com/api/json/ip/{api_key}/{ip_address}"
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            fraud_score = data.get('fraud_score', 'N/A')
            if fraud_score != 'N/A':
                fraud_score = int(fraud_score)
                if fraud_score <= 20:
                    score_description = 'Tốt'
                    emoji = E_CHECK
                elif fraud_score <= 60:
                    score_description = 'Trung bình'
                    emoji = E_WARN
                else:
                    score_description = 'Kém'
                    emoji = E_CROSS
                return fraud_score, score_description, emoji
        return None, None, None
    except Exception as e:
        LOGGER.warning("Lỗi khi lấy điểm IP: %s", e)
        return None, None, None