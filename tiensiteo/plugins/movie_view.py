import aiohttp
import asyncio
import urllib.parse
import logging
from logging import getLogger
from pyrogram import filters
from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
from tiensiteo import app
from tiensiteo.vars import COMMAND_HANDLER

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "TìmPhim"
__HELP__ = """
<blockquote>/xemphim [truy vấn] - Tìm và xem phim qua phimapi
🎬 ⚠️ Lưu ý:
💡 TTJB không lưu trữ phim và không khuyến khích xem phim không bản quyền.
✅ Nếu có thể, hãy sử dụng các nền tảng phim bản quyền để ủng hộ tác giả! 💖</blockquote>
"""

PHIM_API_BASE_URL = "https://phimapi.com/v1/api/tim-kiem"
PHIM_DETAIL_URL = "https://phimapi.com/phim"

RESULTS_PER_PAGE = 6
EPISODES_PER_PAGE = 6
DEFAULT_IMAGE_URL = "https://api.dabeecao.org/data/watch-movie.jpg"

### Xử lý lệnh tìm kiếm phim
@app.on_message(filters.command("xemphim", COMMAND_HANDLER))
async def movie_search_handler(_, message: Message):
    # Kiểm tra nếu lệnh không được sử dụng trong nhóm
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_msg(
            "Lệnh này chỉ hỗ trợ trong nhóm. Hãy tham gia nhóm @thuthuatjb_sp để sử dụng.",
            quote=True,
            del_in=5
        )

    if len(message.command) < 2:
        return await message.reply("❌ Vui lòng nhập từ khóa để tìm kiếm phim.\nVí dụ: `/xemphim người dơi`")

    query = " ".join(message.command[1:])

    # Mã hóa URL để đảm bảo từ khóa không chứa ký tự đặc biệt
    encoded_query = urllib.parse.quote(query)

    reply_msg = await message.reply_photo(
        photo=DEFAULT_IMAGE_URL,
        caption=f"🔍 Đang tìm kiếm phim với từ khóa: `{query}`...",
        quote=True,
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{PHIM_API_BASE_URL}?keyword={encoded_query}&limit=50") as response:
                if response.status != 200:
                    return await reply_msg.edit_caption("❌ Không thể kết nối đến API tìm kiếm phim.")
                
                data = await response.json()
                if not data.get("status") == "success" or not data["data"]["items"]:
                    return await reply_msg.edit_caption(f"❌ Không tìm thấy phim nào với từ khóa: `{query}`.")

                results = data["data"]["items"]
                await send_paginated_results(reply_msg, results, page=1, query=query, user_id=message.from_user.id)

    except Exception as e:
        LOGGER.error(f"Lỗi khi tìm kiếm phim: {e}")
        await reply_msg.edit_caption("❌ Đã xảy ra lỗi khi tìm kiếm phim. Vui lòng thử lại sau.")

### Gửi danh sách kết quả phân trang
async def send_paginated_results(message, results, page, query, user_id):
    # Tính toán số trang
    if not results:  # Trường hợp không có kết quả
        return await message.edit_media(
            media=InputMediaPhoto(
                media=DEFAULT_IMAGE_URL,
                caption=f"🎬 Không tìm thấy kết quả cho: `{query}`."
            ),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Đóng", callback_data=f"close#{user_id}")]]
            ),
        )
    
    total_pages = max(1, (len(results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
    page = max(1, min(page, total_pages))  # Đảm bảo `page` hợp lệ

    # Lấy danh sách kết quả cho trang hiện tại
    start_index = (page - 1) * RESULTS_PER_PAGE
    end_index = min(start_index + RESULTS_PER_PAGE, len(results))
    sliced_results = results[start_index:end_index]

    # Tạo nút
    buttons = []
    for item in sliced_results:
        slug = item["slug"][:50]
        callback_data = f"movie_detail#{slug}#{user_id}"  # Thêm user_id vào callback data
        if len(callback_data) > 64:
            callback_data = callback_data[:60] + "..."  # Cắt callback_data nếu cần
        buttons.append([InlineKeyboardButton(text=item["name"], callback_data=callback_data)])


    # Nút phân trang
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Trước", callback_data=f"search_page#{query}#{page-1}#{user_id}"))
    if page < total_pages:
        pagination_buttons.append(InlineKeyboardButton("➡️ Tiếp", callback_data=f"search_page#{query}#{page+1}#{user_id}"))
    if pagination_buttons:
        buttons.append(pagination_buttons)

    # Nút đóng
    buttons.append([InlineKeyboardButton("❌ Đóng", callback_data=f"close#{user_id}")])

    # Gửi kết quả
    await message.edit_media(
        media=InputMediaPhoto(
            media=DEFAULT_IMAGE_URL,
            caption=f"🎬 Kết quả tìm kiếm cho: `{query}` (Trang {page}/{total_pages})"
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    
### Callback xử lý phân trang tìm kiếm
@app.on_callback_query(filters.regex(r"^search_page#"))
async def search_pagination_handler(_, callback_query):
    _, query, page, user_id = callback_query.data.split("#")
    page = int(page)

    # Kiểm tra quyền truy cập
    if str(callback_query.from_user.id) != user_id:
        return await callback_query.answer("⚠️ Truy cập bị từ chối", show_alert=True)

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{PHIM_API_BASE_URL}?keyword={query}&limit=50") as response:
            if response.status != 200:
                return await callback_query.message.edit_caption("❌ Không thể kết nối đến API tìm kiếm phim.")
            
            data = await response.json()
            results = data["data"]["items"]
            await send_paginated_results(callback_query.message, results, page, query, user_id)

### Callback xử lý chi tiết phim
@app.on_callback_query(filters.regex(r"^movie_detail#"))
async def movie_detail_handler(_, callback_query):
    slug, user_id = callback_query.data.split("#")[1:]

    # Kiểm tra quyền truy cập
    if str(callback_query.from_user.id) != user_id:
        return await callback_query.answer("⚠️ Truy cập bị từ chối", show_alert=True)

    await callback_query.answer("🔍 Đang tải chi tiết phim...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{PHIM_DETAIL_URL}/{slug}") as response:
                if response.status != 200:
                    return await callback_query.message.edit_caption("❌ Không thể kết nối đến API chi tiết phim.")
                
                data = await response.json()
                if not data.get("status"):
                    return await callback_query.message.edit_caption("❌ Không tìm thấy thông tin chi tiết phim.")
                
                movie = data["movie"]
                episodes = data["episodes"][0]["server_data"]
                await send_paginated_episodes(callback_query.message, movie, episodes, page=1, user_id=callback_query.from_user.id)

    except Exception as e:
        LOGGER.error(f"Lỗi khi tải chi tiết phim: {e}")
        await callback_query.message.edit_caption("❌ Đã xảy ra lỗi khi lấy chi tiết phim. Vui lòng thử lại sau.")


### Callback xử lý phân trang tập phim
@app.on_callback_query(filters.regex(r"^episode_page#"))
async def episode_pagination_handler(_, callback_query):
    try:
        _, slug, page, user_id = callback_query.data.split("#")
        page = int(page)

        # Kiểm tra quyền truy cập
        if str(callback_query.from_user.id) != user_id:
            return await callback_query.answer("⚠️ Truy cập bị từ chối", show_alert=True)

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{PHIM_DETAIL_URL}/{slug}") as response:
                if response.status != 200:
                    return await callback_query.message.edit_caption("❌ Không thể kết nối đến API chi tiết phim.")
                
                data = await response.json()
                if not data.get("status"):
                    return await callback_query.message.edit_caption("❌ Không tìm thấy thông tin chi tiết phim.")
                
                movie = data["movie"]
                episodes = data["episodes"][0]["server_data"]

                total_pages = max(1, (len(episodes) + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
                if page < 1 or page > total_pages:
                    return await callback_query.answer("❌ Trang không hợp lệ.", show_alert=True)

                await send_paginated_episodes(callback_query.message, movie, episodes, page, user_id)

    except Exception as e:
        LOGGER.error(f"Lỗi khi phân trang tập phim: {e}")
        await callback_query.message.edit_caption("❌ Đã xảy ra lỗi. Vui lòng thử lại sau.")

### Gửi danh sách tập phim phân trang
MAX_CONTENT_LENGTH = 250  # Giới hạn độ dài của phần content

# Hàm để cắt phần content nếu nó quá dài
def truncate_content(content, max_length=MAX_CONTENT_LENGTH):
    if len(content) > max_length:
        return content[:max_length - 3] + "..."  # Cắt bớt và thêm dấu "..."
    return content

async def send_paginated_episodes(message, movie, episodes, page, user_id):
    # Tính toán số trang
    if not episodes:  # Trường hợp không có tập
        return await message.edit_media(
            media=InputMediaPhoto(
                media=movie["poster_url"],
                caption=f"🎬 **{movie['name']}**\n\n❌ Không tìm thấy danh sách tập phim."
            ),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Đóng", callback_data=f"close#{user_id}")]]
            ),
        )
    
    total_pages = max(1, (len(episodes) + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
    page = max(1, min(page, total_pages))  # Đảm bảo `page` hợp lệ

    # Lấy danh sách tập phim
    start_index = (page - 1) * EPISODES_PER_PAGE
    end_index = min(start_index + EPISODES_PER_PAGE, len(episodes))
    sliced_episodes = episodes[start_index:end_index]

    # Tạo nút: xếp 3 nút 1 hàng
    buttons = []
    row = []
    for i, ep in enumerate(sliced_episodes, start=1):
        link_m3u8 = f"https://api.dabeecao.org/player?url={ep['link_m3u8']}"
        row.append(InlineKeyboardButton(text=ep["name"], url=link_m3u8))
        if i % 3 == 0 or i == len(sliced_episodes):  # Khi đủ 3 nút hoặc là nút cuối cùng
            buttons.append(row)
            row = []

    # Nút phân trang
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Trước", callback_data=f"episode_page#{movie['slug']}#{page-1}#{user_id}"))
    if page < total_pages:
        pagination_buttons.append(InlineKeyboardButton("➡️ Tiếp", callback_data=f"episode_page#{movie['slug']}#{page+1}#{user_id}"))
    if pagination_buttons:
        buttons.append(pagination_buttons)

    # Nút đóng
    buttons.append([InlineKeyboardButton("❌ Đóng", callback_data=f"close#{user_id}")])

    # Cắt phần nội dung movie['content'] nếu quá dài
    truncated_content = truncate_content(movie['content'])

    # Gửi thông tin phim và danh sách tập
    text = (
        f"🎬 **{movie['name']}**\n"
        f"📅 Năm: {movie['year']}\n"
        f"🕒 Thời lượng: {movie['time']}\n"
        f"🌍 Quốc gia: {', '.join(c['name'] for c in movie['country'])}\n"
        f"📄 Nội dung: {truncated_content}\n\n"
        f"🎬 **⚠️ Lưu ý:**\n💡 TTJB không lưu trữ phim và không khuyến khích xem phim không bản quyền.\n✅ Nếu có thể, hãy sử dụng các nền tảng phim bản quyền để ủng hộ tác giả! 💖**\n\n"
        f"**Danh sách tập:** Trang {page}/{total_pages}"
    )

    await message.edit_media(
        media=InputMediaPhoto(
            media=movie["poster_url"],
            caption=text,
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


### Callback đóng tin nhắn
@app.on_callback_query(filters.regex(r"^close#"))
async def close_callback(_, callback_query):
    user_id = callback_query.data.split("#")[1]

    # Kiểm tra quyền truy cập
    if str(callback_query.from_user.id) != user_id:
        return await callback_query.answer("⚠️ Truy cập bị từ chối", show_alert=True)

    await callback_query.message.delete()