import os
import shutil
import aiohttp
import asyncio
import logging
from logging import getLogger

from re import findall
from bing_image_downloader import downloader
from pyrogram import enums, filters
from pyrogram.types import InputMediaPhoto, Message
from PIL import Image, UnidentifiedImageError

from dorasuper import app
from dorasuper.emoji import E_NOTE, E_PHOTO, E_WARN
from dorasuper.core.decorator.errors import capture_err
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")

__MODULE__ = "TìmKiếmẢnh"
__HELP__ = """
<blockquote>/timanh [từ khóa] [lim=số lượng] - Tìm và gửi lại hình ảnh từ Bing. Mặc định 6 ảnh.
/hinhnen [từ khóa] - Tìm hình nền từ Unsplash với từ khóa được cung cấp. Yêu cầu từ khóa.
Lưu ý: Mỗi người dùng chỉ được sử dụng các lệnh này tối đa 2 lần liên tiếp.</blockquote>
"""

# Khóa API Unsplash
UNSPLASH_ACCESS_KEY = ""

# Bộ đếm chung cho cả hai lệnh
request_count = {}

async def get_wallpapers(query, count=6):
    url = f"https://api.unsplash.com/photos/random?query={query}&count={count}&client_id={UNSPLASH_ACCESS_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return [
                    InputMediaPhoto(
                        photo['urls']['regular'],
                        caption=f"{E_PHOTO} Photo by {photo['user']['name']}\n{E_NOTE} {photo.get('alt_description', 'No description available')}"
                    )
                    for photo in data
                ]
            else:
                print("Error:", response.status)
                return []

# Hàm thay đổi kích thước ảnh
def resize_image(image_path, max_size=1280):
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_size, max_size), Image.LANCZOS)  # Giữ tỷ lệ, giới hạn kích thước
            new_path = os.path.splitext(image_path)[0] + "_resized.jpg"
            img.save(new_path, "JPEG", quality=95)
            return new_path
    except Exception as e:
        print(f"Error resizing image: {e}")
        return None

# Lệnh timanh
@app.on_message(filters.command(["timanh"], COMMAND_HANDLER))
@capture_err
async def timanh_command(_, ctx: Message):
    user_id = ctx.from_user.id
    msg = await ctx.reply_msg("Đang xử lý tìm kiếm ảnh, vui lòng đợi...", quote=True)

    # Khởi tạo số lần yêu cầu
    if user_id not in request_count:
        request_count[user_id] = 0

    # Kiểm tra giới hạn 2 lần
    if request_count[user_id] >= 2:
        await msg.edit_msg(f"{E_WARN} Bạn chỉ được sử dụng lệnh này tối đa 2 lần liên tiếp. Vui lòng đợi người khác sử dụng trước khi thử lại.", parse_mode=enums.ParseMode.HTML)
        await asyncio.sleep(5)
        await msg.delete()
        return

    try:
        query = ctx.text.split(None, 1)[1]
    except IndexError:
        await msg.edit_msg("Vui lòng cung cấp từ khóa tìm kiếm ảnh!")
        await asyncio.sleep(5)
        await msg.delete()
        return

    lim = findall(r"lim=\d+", query)
    try:
        lim = int(lim[0].replace("lim=", ""))
        query = query.replace(f"lim={lim}", "")
    except IndexError:
        lim = 6

    download_dir = "downloads"
    images_dir = os.path.join(download_dir, query.strip())

    try:
        downloader.download(
            query.strip(),
            limit=lim,
            output_dir=download_dir,
            adult_filter_off=True,
            force_replace=False,
            timeout=60
        )
        if not os.path.exists(images_dir) or not os.listdir(images_dir):
            raise ValueError("Không tìm thấy ảnh nào.")

        # Kiểm tra và xử lý ảnh
        images = []
        valid_extensions = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
        for img in os.listdir(images_dir)[:lim]:
            img_path = os.path.join(images_dir, img)
            if not img.lower().endswith(valid_extensions):
                continue
            try:
                # Thay đổi kích thước ảnh
                resized_path = resize_image(img_path)
                if resized_path:
                    images.append(resized_path)
                    if resized_path != img_path:
                        os.remove(img_path)  # Xóa ảnh gốc nếu đã thay đổi
            except (UnidentifiedImageError, OSError):
                continue

        if not images:
            raise ValueError("Không tìm thấy ảnh hợp lệ sau khi kiểm tra.")

        media = [InputMediaPhoto(media=img) for img in images]

        count = 0
        for _ in images:
            count += 1
            await msg.edit_msg(f"Đã tìm thấy {count} ảnh, đang xử lý để tải lên...")

        await app.send_media_group(
            chat_id=ctx.chat.id,
            media=media,
            reply_to_message_id=ctx.id
        )
        request_count[user_id] += 1

        # Reset số lần yêu cầu của người dùng khác
        for uid in request_count:
            if uid != user_id:
                request_count[uid] = 0

        # Xóa tin nhắn xử lý sau khi tải lên thành công
        await msg.delete()

    except (ValueError, OSError, UnidentifiedImageError) as e:
        await msg.edit_msg(f"Lỗi: {str(e)}")
        await asyncio.sleep(5)
        await msg.delete()
    except Exception as e:
        await msg.edit_msg(f"Lỗi không xác định: {str(e)}")
        await asyncio.sleep(5)
        await msg.delete()
    finally:
        if os.path.exists(images_dir):
            shutil.rmtree(images_dir)

# Lệnh hinhnen
@app.on_message(filters.command(["hinhnen"], COMMAND_HANDLER))
@capture_err
async def hinhnen_command(_, ctx: Message):
    user_id = ctx.from_user.id
    command = ctx.text.split()
    msg = await ctx.reply_msg("Đang tìm hình nền, vui lòng đợi...", quote=True)

    # Khởi tạo số lần yêu cầu
    if user_id not in request_count:
        request_count[user_id] = 0

    # Kiểm tra giới hạn 2 lần
    if request_count[user_id] >= 2:
        await msg.edit_msg(f"{E_WARN} Bạn chỉ được sử dụng lệnh này tối đa 2 lần liên tiếp. Vui lòng đợi người khác sử dụng trước khi thử lại.", parse_mode=enums.ParseMode.HTML)
        await asyncio.sleep(5)
        await msg.delete()
        return

    # Yêu cầu từ khóa
    try:
        query = " ".join(command[1:])
    except IndexError:
        await msg.edit_msg("Vui lòng cung cấp từ khóa tìm kiếm hình nền!")
        await asyncio.sleep(5)
        await msg.delete()
        return

    wallpapers = await get_wallpapers(query)
    if wallpapers:
        await app.send_media_group(
            chat_id=ctx.chat.id,
            media=wallpapers,
            reply_to_message_id=ctx.id
        )
        request_count[user_id] += 1

        # Reset số lần yêu cầu của người dùng khác
        for uid in request_count:
            if uid != user_id:
                request_count[uid] = 0
    else:
        await msg.edit_msg("Không tìm thấy hình nền nào, vui lòng thử lại sau.")
        await asyncio.sleep(5)

    await msg.delete()