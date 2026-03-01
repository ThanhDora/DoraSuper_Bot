import aiohttp
from logging import getLogger

from pyrogram import enums, filters
from dorasuper import app
from dorasuper.emoji import (
    E_FIRE,
    E_GLOBE,
    E_ICE,
    E_MAYCUTE,
    E_PIN_LOC,
    E_RAIN,
    E_RAINBOW,
    E_SNOW,
    E_STAT,
    E_SUNNY,
    E_THUNDER,
    E_WAIT,
    E_WARN,
)
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")

# Open-Meteo: miễn phí, không cần API key
# https://open-meteo.com/

# WMO weather_code -> (tiếng Việt, emoji từ dorasuper.emoji)
def _wmo_emojis():
    return {
        0: ("Trời quang", E_SUNNY),
        1: ("Chủ yếu quang đãng", E_SUNNY),
        2: ("Có mây", E_MAYCUTE),
        3: ("Nhiều mây", E_MAYCUTE),
        45: ("Sương mù", E_MAYCUTE),
        48: ("Sương mù đóng băng", E_MAYCUTE),
        51: ("Mưa phùn nhẹ", E_RAIN),
        53: ("Mưa phùn vừa", E_RAIN),
        55: ("Mưa phùn dày", E_RAIN),
        56: ("Mưa phùn lạnh nhẹ", E_RAIN),
        57: ("Mưa phùn lạnh dày", E_RAIN),
        61: ("Mưa nhẹ", E_RAIN),
        63: ("Mưa vừa", E_RAIN),
        65: ("Mưa to", E_RAIN),
        66: ("Mưa lạnh nhẹ", E_RAIN),
        67: ("Mưa lạnh to", E_RAIN),
        71: ("Tuyết nhẹ", E_SNOW),
        73: ("Tuyết vừa", E_SNOW),
        75: ("Tuyết dày", E_SNOW),
        77: ("Mưa tuyết", E_SNOW),
        80: ("Mưa rào nhẹ", E_RAIN),
        81: ("Mưa rào vừa", E_RAIN),
        82: ("Mưa rào to", E_THUNDER),
        85: ("Mưa tuyết nhẹ", E_SNOW),
        86: ("Mưa tuyết to", E_SNOW),
        95: ("Dông", E_THUNDER),
        96: ("Dông có mưa đá nhẹ", E_THUNDER),
        99: ("Dông có mưa đá to", E_THUNDER),
    }


WEATHER_DESC = _wmo_emojis()


def wmo_to_desc(code: int) -> tuple[str, str]:
    """Trả về (mô tả, emoji)."""
    if code in WEATHER_DESC:
        return WEATHER_DESC[code]
    for k, v in sorted(WEATHER_DESC.items(), reverse=True):
        if code >= k:
            return v
    return ("Không xác định", E_RAINBOW)


async def geocode(city: str) -> dict | None:
    """Tìm tọa độ từ tên thành phố (Open-Meteo Geocoding API)."""
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=vi"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            results = data.get("results", [])
            return results[0] if results else None


async def get_forecast(lat: float, lon: float, tz: str = "Asia/Ho_Chi_Minh") -> dict | None:
    """Lấy thời tiết hiện tại (Open-Meteo Forecast API)."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
        f"&timezone={tz}"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


def format_weather_message(loc_name: str, data: dict) -> str:
    cur = data.get("current", {})

    temp = cur.get("temperature_2m", 0)
    feels = cur.get("apparent_temperature", temp)
    humidity = cur.get("relative_humidity_2m", 0)
    wind = cur.get("wind_speed_10m", 0)
    code = cur.get("weather_code", 0)
    desc, emoji = wmo_to_desc(code)

    msg = (
        f"{E_SUNNY} <b>Thời tiết tại {loc_name}</b>\n\n"
        f"{emoji} <b>Mô tả:</b> {desc}\n"
        f"{E_STAT} <b>Nhiệt độ:</b> {temp:.0f}°C (Cảm giác: {feels:.0f}°C)\n"
        f"{E_STAT} <b>Độ ẩm:</b> {humidity}%\n"
        f"{E_STAT} <b>Tốc độ gió:</b> {wind} km/h\n"
    )

    if temp < 20:
        msg += f"\n{E_ICE} Nên mặc ấm để tránh lạnh."
    elif temp > 30:
        msg += f"\n{E_FIRE} Hãy uống nhiều nước và tránh nắng gắt."

    return msg


@app.on_message(filters.command("thoitiet", COMMAND_HANDLER))
async def weather_command(client, message):
    parts = message.text.split(maxsplit=1)
    city = parts[1].strip() if len(parts) > 1 else None

    status_msg = await message.reply(f"{E_WAIT} Đang phân tích thời tiết...", parse_mode=enums.ParseMode.HTML)

    if not city:
        cities = ["Hà Nội", "Thành phố Hồ Chí Minh"]
        responses = []
        for c in cities:
            loc = await geocode(c)
            if loc:
                lat = loc["latitude"]
                lon = loc["longitude"]
                name = loc.get("name", c)
                data = await get_forecast(lat, lon)
                if data:
                    responses.append(format_weather_message(name, data))
                else:
                    responses.append(f"{E_WARN} Không lấy được dữ liệu thời tiết cho: {c}")
            else:
                responses.append(f"{E_WARN} Không tìm thấy: {c}")
        responses.append(f"{E_GLOBE} Bạn có thể nhập tên thành phố để xem thời tiết nơi khác. {E_PIN_LOC}")
        await status_msg.edit_text("\n\n".join(responses), parse_mode=enums.ParseMode.HTML)
        return

    loc = await geocode(city)
    if not loc:
        await status_msg.edit_text(
            f"{E_WARN} Không tìm thấy thành phố. Thử tên tiếng Anh (vd: Hanoi, Da Nang).",
            parse_mode=enums.ParseMode.HTML,
        )
        return

    lat = loc["latitude"]
    lon = loc["longitude"]
    name = loc.get("name", city)
    data = await get_forecast(lat, lon)
    if not data:
        await status_msg.edit_text(f"{E_WARN} Không lấy được dữ liệu thời tiết.", parse_mode=enums.ParseMode.HTML)
        return

    text = format_weather_message(name, data)
    await status_msg.edit_text(text, parse_mode=enums.ParseMode.HTML)
