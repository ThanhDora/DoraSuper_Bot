import io
import zipfile
import shutil
import tempfile
import asyncio
import math
import os
import re
import time
import aiohttp
import pytz
import subprocess
import random
import string
from logging import getLogger
from datetime import datetime, timedelta
from urllib.parse import unquote

from bs4 import BeautifulSoup
from cloudscraper import create_scraper
from pyrogram import filters, enums
from pyrogram.file_id import FileId
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatMemberStatus as CMS
from pySmartDL import SmartDL

from dorasuper import app
from dorasuper.core.decorator import capture_err, new_task
from dorasuper.emoji import E_DOWNLOAD, E_LINK, E_LOADING, E_ERROR, E_SUCCESS
from dorasuper.helper.http import fetch
from dorasuper.helper.pyro_progress import humanbytes, progress_for_pyrogram
from dorasuper.vars import (
    COMMAND_HANDLER,
    SUDO,
    USE_GDRIVE,
    GDRIVE_CREDENTIALS_PATH,
    GDRIVE_FOLDER_ID,
    TMPFILES_UPLOAD_FIELD,
)

LOGGER = getLogger("DoraSuper")

__MODULE__ = "TảiVề"
__HELP__ = """
<blockquote><u>Tải tệp:</u>
/getfile [url/trả lời tệp] - Tải xuống tệp (chủ bot)
/getdirect [trả lời tệp] - Tải tệp lên tmpfiles hoặc Google Drive để lấy link

<u>Tải Video TikTok:</u>
/dl [link] - Tải video/ảnh từ TikTok
/tt [link] - Viết tắt của /dl
/autodl - Bật/tắt tự động nhận link trong nhóm (admin)
Gửi link TikTok → bot tự tải (trong nhóm cần bật /autodl trước)</blockquote>
"""
async def auto_delete_message(message, delay=1800):
    await asyncio.sleep(delay)
    await message.delete()

# tmpfiles.org chính thức: https://tmpfiles.org/api (file tự xóa sau 60 phút, tối đa 100 MB)
API_UPLOAD_URL = "https://tmpfiles.org/api/v1/upload"
TIMEOUT_MINUTES = 60


def _upload_to_gdrive_sync(file_path: str, filename: str) -> str:
    """Upload file lên Google Drive. Bắt buộc dùng thư mục trong Shared Drive (Service Account không có quota)."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if not GDRIVE_FOLDER_ID:
        raise ValueError(
            "GDRIVE_FOLDER_ID chưa cấu hình. Tạo Shared Drive (Drive → New → Shared drive), "
            "thêm email Service Account (trong file JSON) vào Shared Drive với quyền Content manager, "
            "mở Shared Drive → copy ID từ URL (dạng .../folders/XXXX) vào GDRIVE_FOLDER_ID."
        )
    creds = Credentials.from_service_account_file(
        GDRIVE_CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    drive = build("drive", "v3", credentials=creds)
    media = MediaFileUpload(file_path, resumable=True)
    meta = {"name": filename, "parents": [GDRIVE_FOLDER_ID]}
    file = drive.files().create(
        body=meta,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    file_id = file.get("id")
    drive.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
        supportsAllDrives=True,
    ).execute()
    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"

@app.on_message(filters.command(["getdirect"], COMMAND_HANDLER))
async def getdirect_handler(bot, message):
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply("Lệnh này chỉ hỗ trợ trong nhóm. Hãy tham gia nhóm @thuthuatjb_sp để sử dụng.")
    
    if not message.reply_to_message:
        return await message.reply(f"{E_ERROR} Vui lòng trả lời tập tin phương tiện.")
    
    reply = message.reply_to_message
    media = reply.document or reply.video or reply.audio
    if not media and reply.photo:
        media = reply.photo[-1]  # largest photo size
    if not media:
        return await message.reply(f"{E_ERROR} Loại phương tiện không được hỗ trợ.")
    
    m = await message.reply(f"{E_LOADING} Tải tập tin của bạn xuống máy chủ của tôi...")
    now = time.time()
    dc_id = FileId.decode(media.file_id).dc_id
    fileku = await message.reply_to_message.download(
        progress=progress_for_pyrogram,
        progress_args=(f"{E_LOADING} Đang cố tải về, xin chờ..", m, now, dc_id),
    )
    
    try:
        filename = os.path.basename(fileku) or "file"

        if USE_GDRIVE and GDRIVE_CREDENTIALS_PATH and os.path.exists(GDRIVE_CREDENTIALS_PATH):
            await m.edit(f"{E_LOADING} Đang tải lên Google Drive, xin chờ..")
            file_url = await asyncio.to_thread(_upload_to_gdrive_sync, fileku, filename)
            output = (
                f"{E_SUCCESS} Đã tải lên Google Drive.\n\n"
                f"{E_DOWNLOAD} Link: <code>{file_url}</code>"
            )
            btn = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(f"{E_LINK} Mở / Chia sẻ", url=file_url)],
                    [InlineKeyboardButton("Chia sẻ", url=f"https://t.me/share/url?url={file_url}")],
                ]
            )
            await m.edit(output, reply_markup=btn, parse_mode=enums.ParseMode.HTML)
        else:
            await m.edit(f"{E_LOADING} Đang tải lên tmpfiles, xin chờ..")
            with open(fileku, "rb") as f:
                file_content = f.read()
            form = aiohttp.FormData()
            # Gửi dạng file-like (BytesIO) + filename để server nhận đúng phần file
            form.add_field(
                TMPFILES_UPLOAD_FIELD,
                io.BytesIO(file_content),
                filename=filename,
                content_type="application/octet-stream",
            )
            async with aiohttp.ClientSession() as session:
                async with session.post(API_UPLOAD_URL, data=form) as response:
                    try:
                        response_json = await response.json()
                    except Exception:
                        text = await response.text()
                        raise ValueError(f"API trả về không phải JSON: {text[:200]}")
            
            file_url = response_json.get("url") or (response_json.get("data") or {}).get("url")
            if file_url:
                tz = pytz.timezone("Asia/Ho_Chi_Minh")
                expiration_time = datetime.now(tz) + timedelta(minutes=TIMEOUT_MINUTES)
                expiration_str = expiration_time.strftime("%H:%M:%S %d/%m/%Y")
                output = (
                    f"{E_SUCCESS} Tệp đã tải lên tmpfiles. Liên kết có hiệu lực trong {TIMEOUT_MINUTES} phút (hết hạn {expiration_str}).\n\n"
                    f"{E_DOWNLOAD} Link: <code>{file_url}</code>"
                )
                btn = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(f"Chia sẻ liên kết", url=f"https://t.me/share/url?url={file_url}")]]
                )
                await m.edit(output, reply_markup=btn, parse_mode=enums.ParseMode.HTML)
            else:
                err_msg = response_json.get("message") or response_json.get("error") or str(response_json)
                await m.edit(f"{E_ERROR} Đã xảy ra lỗi khi tải lên: {err_msg}")
        
    except Exception as e:
        LOGGER.exception("getdirect: %s", e)
        await m.edit(f"{E_ERROR} Đã xảy ra lỗi!\n\n{type(e).__name__}: {e}")
        
    finally:
        if fileku and os.path.exists(fileku):
            try:
                os.remove(fileku)
            except OSError:
                pass
    await auto_delete_message(m, TIMEOUT_MINUTES * 60)
    
API_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
UPLOAD_TIME = "1h"
MAX_FILE_SIZE_MB = 1024  # 1GB = 1024MB

ASSETS_DIR = "/www/wwwroot/tiensi-teo-bot/assets"
GETINSTALL_DIR = os.path.join(ASSETS_DIR, "getinstall")
DYLIB_DIR = os.path.join(ASSETS_DIR, "dylib")
SATELLA_PATH = os.path.join(DYLIB_DIR, "SatellaJailed.dylib")
FIX_PATH = os.path.join(DYLIB_DIR, "Fix_Sideload_TTJB.dylib")
FIX1_PATH = os.path.join(DYLIB_DIR, "Fix_Sideload_1_TTJB.dylib")
FIX2_PATH = os.path.join(DYLIB_DIR, "Fix_Sideload_2_TTJB.dylib")
ADBLOCK_PATH = os.path.join(DYLIB_DIR, "Adblock.dylib")
EXTENSIONFIX_PATH = os.path.join(DYLIB_DIR, "ExtensionFix_TTJB.dylib")
P12_PATH = os.path.join(GETINSTALL_DIR, "cer.p12")
MOBILEPROVISION_PATH = os.path.join(GETINSTALL_DIR, "cer.mobileprovision")
ZSIGN_PATH = "/usr/local/bin/zsign"

def generate_random_filename(extension=".ipa"):
    """Hàm tạo tên tệp ngẫu nhiên với phần mở rộng được chỉ định."""
    random_name = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"{random_name}{extension}"

#@app.on_message(filters.command(["getinstall"], COMMAND_HANDLER))
async def upload(bot, message):
    # Kiểm tra nếu tin nhắn không phải là trong nhóm
    if message.chat.type != enums.ChatType.GROUP and message.chat.type != enums.ChatType.SUPERGROUP:
        return await message.reply("Lệnh này chỉ hỗ trợ trong nhóm. Hãy tham gia nhóm @thuthuatjb_sp để sử dụng.")
    
    if not message.reply_to_message:
        return await message.reply(f"{E_ERROR} Vui lòng trả lời tập tin .ipa hoặc .tipa bằng lệnh")
    
    media = message.reply_to_message.document
    if not media or not media.file_name.endswith(('.ipa', '.tipa')):
        return await message.reply("Chỉ hỗ trợ tệp .ipa hoặc .tipa.")
    
    # Kiểm tra kích thước tập tin
    file_size_mb = media.file_size / (1024 * 1024)  # Kích thước tập tin tính bằng MB
    if file_size_mb > MAX_FILE_SIZE_MB:
        return await message.reply("Tệp quá lớn. Vui lòng chỉ tải lên các tập tin dưới 1GB.")
    
    m = await message.reply("Đang tải tập tin của bạn xuống máy chủ xử lý...")
    now = time.time()
    dc_id = FileId.decode(media.file_id).dc_id
    original_file_path = await message.reply_to_message.download(
        file_name=os.path.join(ASSETS_DIR, generate_random_filename()),
        progress=progress_for_pyrogram,
        progress_args=("Đang cố tải về, xin chờ..", m, now, dc_id),
    )

    original_file_name = media.file_name  # Lưu lại tên tệp gốc

    # Đổi tên file thành tên ngẫu nhiên với đuôi .ipa nếu cần
    if original_file_path.endswith('.tipa'):
        new_file_path = original_file_path.replace('.tipa', '.ipa')
        os.rename(original_file_path, new_file_path)
        original_file_path = new_file_path

    # Tạo tên tệp đầu ra với tên ngẫu nhiên có hậu tố "_output.ipa"
    output_file_path = original_file_path.replace(".ipa", "_output.ipa")

    # Kiểm tra sự tồn tại của các tệp và đường dẫn
    if not os.path.exists(P12_PATH):
        await m.edit(f"Tệp chứng chỉ không tồn tại: {P12_PATH}")
        return
    if not os.path.exists(MOBILEPROVISION_PATH):
        await m.edit(f"Tệp mobileprovision không tồn tại: {MOBILEPROVISION_PATH}")
        return
    if not os.path.exists(original_file_path):
        await m.edit(f"Tệp IPA không tồn tại: {original_file_path}")
        return
    if not os.path.exists(ZSIGN_PATH):
        await m.edit(f"Tệp thực thi zsign không tồn tại: {ZSIGN_PATH}")
        return

    try:
        # Gửi thông báo bắt đầu ký
        await m.edit("Đang tiến hành ký tệp của bạn, xin chờ...")

        # Ký file bằng zsign và lưu vào đường dẫn chỉ định
        command = f"{ZSIGN_PATH} -z 6 -k {P12_PATH} -p TTJB -m {MOBILEPROVISION_PATH} -o {output_file_path} {original_file_path}"
        
        # Chạy lệnh zsign bằng subprocess và ghi cả stdout và stderr
        result = subprocess.run(
            ['sh', '-c', command], 
            cwd=GETINSTALL_DIR,  # Chạy lệnh trong thư mục getinstall
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            env=os.environ.copy()
        )

        # Kiểm tra xem có lỗi không
        if result.returncode != 0:
            # Có lỗi xảy ra, thông báo người dùng liên hệ để báo lỗi
            await m.edit(f"Đã xảy ra lỗi khi ký tệp. Vui lòng liên hệ @dabeecao để báo lỗi.")
            return
        
        # Gửi thông báo ký thành công
        await m.edit("Tệp của bạn đã được ký thành công. Đang tải lên máy chủ lưu trữ, xin chờ...")
        
        # Tạo đối tượng FormData để gửi file đã ký
        async with aiohttp.ClientSession() as session:
            with open(output_file_path, 'rb') as f:
                form = aiohttp.FormData()
                form.add_field('reqtype', 'fileupload')
                form.add_field('time', UPLOAD_TIME)
                form.add_field('fileToUpload', f, filename=os.path.basename(output_file_path))

                async with session.post(API_URL, data=form) as response:
                    # Lấy phản hồi dưới dạng văn bản
                    response_text = await response.text()
                    
                    # Kiểm tra và trích xuất URL từ phản hồi
                    if response_text.startswith("http"):
                        file_url = response_text.strip()  # Loại bỏ khoảng trắng không cần thiết
                        troll_url = f"apple-magnifier://install?url={file_url}"
                        install_url = f"https://dl.thuthuatjb.com/ipa/install.html?url={file_url}"
                        
                        # Tính thời gian hết hạn với múi giờ Asia/Ho_Chi_Minh (UTC+7)
                        tz = pytz.timezone('Asia/Ho_Chi_Minh')
                        expiration_time = datetime.now(tz) + timedelta(hours=1)
                        expiration_str = expiration_time.strftime("%H:%M:%S %d/%m/%Y")
                        
                        output = (
                            f'<b>Đã ký tệp và tạo liên kết thành công. Tên tệp được ký: {original_file_name}</b>\n\nLưu ý ipa được ký thông qua chứng chỉ miễn phí, sẽ không cài đặt thành công nếu chứng chỉ hết hạn hoặc thiết bị của bạn bị blacklist với chứng chỉ.\n\nBạn phải bật URL Scheme Enabled trong tab Settings của Trollstore để cài được qua Trollstore.\n\n<b>Liên kết có hiệu lực trong 1 tiếng và sẽ hết hạn vào lúc {expiration_str}</b>.'
                        )
                        btn = InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton("qua Trollstore", url=f"https://api.dabeecao.org/data/urlscheme/index.php?url={troll_url}"),
                                    InlineKeyboardButton("qua OTA", url=install_url),
                                ],
                                [
                                    InlineKeyboardButton("Ủng hộ DoraSuper", url="https://thanhdora3605.dev")
                                ]
                            ]
                        )
                        await m.edit(output, reply_markup=btn)
                        
                        # Xóa các file tạm ngay sau khi hoàn tất
                        if os.path.exists(original_file_path):
                            os.remove(original_file_path)
                        if os.path.exists(output_file_path):
                            os.remove(output_file_path)
                        
                        # Xóa tin nhắn sau 60 phút
                        await auto_delete_message(m, TIMEOUT_MINUTES * 60)  # 60 phút
                    else:
                        await m.edit(f"Đã xảy ra lỗi khi tải lên file. Vui lòng thử lại sau hoặc báo lỗi cho @dabeecao")
    except subprocess.CalledProcessError:
        # Xử lý lỗi khi chạy lệnh zsign
        await m.edit("Đã xảy ra lỗi khi ký tệp. Vui lòng liên hệ @dabeecao để báo lỗi.")
    except Exception as e:
        await bot.send_message(message.chat.id, text="Đã xảy ra lỗi! Vui lòng liên hệ @dabeecao để báo lỗi.")
    finally:
        # Xóa các file tạm trong trường hợp có lỗi xảy ra
        if os.path.exists(original_file_path):
            os.remove(original_file_path)
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
            
@app.on_message(filters.command(["cloneapp"], COMMAND_HANDLER))
async def cloneapp_handler(bot, message):
    # Kiểm tra nếu tin nhắn không phải là trong nhóm
    if message.chat.type != enums.ChatType.GROUP and message.chat.type != enums.ChatType.SUPERGROUP:
        return await message.reply("Lệnh này chỉ hỗ trợ trong nhóm. Hãy tham gia nhóm @DoraTeamMods để sử dụng.")
    
    if not message.reply_to_message:
        return await message.reply("Vui lòng trả lời tập tin .ipa hoặc .tipa bằng lệnh.")
    
    media = message.reply_to_message.document
    if not media or not media.file_name.endswith(('.ipa', '.tipa')):
        return await message.reply("Chỉ hỗ trợ tệp .ipa hoặc .tipa.")
    
    # Kiểm tra kích thước tập tin
    file_size_mb = media.file_size / (1024 * 1024)  # Kích thước tập tin tính bằng MB
    if file_size_mb > MAX_FILE_SIZE_MB:
        return await message.reply("Tệp quá lớn. Vui lòng chỉ tải lên các tập tin dưới 1GB.")
    
    m = await message.reply("Đang tải tập tin của bạn xuống máy chủ xử lý...")
    now = time.time()
    dc_id = FileId.decode(media.file_id).dc_id
    original_file_path = await message.reply_to_message.download(
        file_name=os.path.join(ASSETS_DIR, generate_random_filename()),
        progress=progress_for_pyrogram,
        progress_args=("Đang cố tải về, xin chờ..", m, now, dc_id),
    )

    original_file_name = media.file_name  # Lưu lại tên tệp gốc

    # Đổi tên file thành tên ngẫu nhiên với đuôi .ipa nếu cần
    if original_file_path.endswith('.tipa'):
        new_file_path = original_file_path.replace('.tipa', '.ipa')
        os.rename(original_file_path, new_file_path)
        original_file_path = new_file_path

    # Tạo tên tệp đầu ra với tên ngẫu nhiên có hậu tố "_output.ipa"
    output_file_path = original_file_path.replace(".ipa", "_output.ipa")

    # Lấy tên ngẫu nhiên từ tệp tải xuống không có đuôi .ipa
    random_name = os.path.basename(original_file_path).replace('.ipa', '')

    # Kiểm tra sự tồn tại của các tệp và đường dẫn
    if not os.path.exists(original_file_path):
        await m.edit(f"Tệp IPA không tồn tại: {original_file_path}")
        return

    try:
        # Gửi thông báo bắt đầu ký
        await m.edit("Đang tiến hành nhân bản tệp của bạn, xin chờ...")

        # Ký file bằng và thay đổi bundle id
        command = f"/root/.local/bin/cyan -o {output_file_path} -i {original_file_path} -b com.thuthuatjb.{random_name}"
        
        # Chạy lệnh zsign bằng subprocess và ghi cả stdout và stderr
        result = subprocess.run(
            ['sh', '-c', command], 
            cwd=GETINSTALL_DIR,  # Chạy lệnh trong thư mục getinstall
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            env=os.environ.copy()
        )

        # Kiểm tra xem có lỗi không
        if result.returncode != 0:
            # Có lỗi xảy ra, thông báo người dùng liên hệ để báo lỗi
            await m.edit(f"Đã xảy ra lỗi khi nhân bản. Vui lòng liên hệ @dabeecao để báo lỗi.")
            return
        
        # Gửi thông báo ký thành công
        await m.edit("Tệp của bạn đã được nhân bản thành công. Đang gửi lại tệp, xin chờ...")

        # Gửi tệp đã ký lên Telegram
        signed_file_name = f"{original_file_name.replace('.ipa', '')}_clone_TTJB.ipa"
        await message.reply_document(
            document=output_file_path,
            file_name=signed_file_name,
            caption=f"Đã nhân bản thành công {original_file_name} thành {signed_file_name}\n\nMỗi lần dùng lệnh nhân bản sẽ luôn tạo ra ứng dụng không bao giờ trùng lặp. Nhấn /donate cho tiến sĩ nếu bạn thấy hữu ích nhé."
        )

        # Xoá tin nhắn thông báo
        await m.delete()

    except subprocess.CalledProcessError:
        # Xử lý lỗi khi chạy lệnh zsign
        await m.edit("Đã xảy ra lỗi khi nhân bản. Vui lòng liên hệ @dabeecao để báo lỗi.")
    except Exception as e:
        await bot.send_message(message.chat.id, text="Đã xảy ra lỗi! Vui lòng liên hệ @dabeecao để báo lỗi.")
    finally:
        # Xóa các file tạm trong trường hợp có lỗi xảy ra
        if os.path.exists(original_file_path):
            os.remove(original_file_path)
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
            
@app.on_message(filters.command(["inject_iap"], COMMAND_HANDLER))
async def inject_iap_handler(bot, message):
    # Kiểm tra nếu tin nhắn không phải là trong nhóm
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply("Lệnh này chỉ hỗ trợ trong nhóm. Hãy tham gia nhóm @thuthuatjb_sp để sử dụng.")

    # Kiểm tra nếu người dùng trả lời tin nhắn có file đính kèm
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("Vui lòng trả lời tập tin .ipa hoặc .tipa bằng lệnh.")

    media = message.reply_to_message.document
    if not media.file_name.endswith(('.ipa', '.tipa')):
        return await message.reply("Chỉ hỗ trợ tệp .ipa hoặc .tipa.")
    
    # Kiểm tra kích thước tập tin
    file_size_mb = media.file_size / (1024 * 1024)  # Kích thước tập tin tính bằng MB
    if file_size_mb > MAX_FILE_SIZE_MB:
        return await message.reply("Tệp quá lớn. Vui lòng chỉ tải lên các tập tin dưới 1GB.")

    # Kiểm tra sự tồn tại của các tệp và đường dẫn cần thiết
    required_files = {
        "ADBLOCK": ADBLOCK_PATH,
        "SATELLA": SATELLA_PATH,
    }
    for name, path in required_files.items():
        if not os.path.exists(path):
            return await message.reply(f"Tệp {name} không tồn tại: {path}")

    # Tải file xuống
    m = await message.reply("Đang tải tập tin của bạn xuống máy chủ xử lý...")
    now = time.time()
    dc_id = FileId.decode(media.file_id).dc_id
    original_file_path = await message.reply_to_message.download(
        file_name=os.path.join(ASSETS_DIR, generate_random_filename()),
        progress=progress_for_pyrogram,
        progress_args=("Đang cố tải về, xin chờ..", m, now, dc_id),
    )

    original_file_name = media.file_name  # Lưu lại tên tệp gốc
    
    # Đổi tên file thành .ipa nếu cần
    if original_file_path.endswith('.tipa'):
        new_file_path = original_file_path.replace('.tipa', '.ipa')
        os.rename(original_file_path, new_file_path)
        original_file_path = new_file_path

    output_file_path = original_file_path.replace(".ipa", "_output.ipa")
    signed_file_name = f"{os.path.basename(original_file_name).replace('.ipa', '')}_iap_noads_TTJB.ipa"
    temp_files = []  # Danh sách để lưu các tệp tạm

    try:
        # Tiêm từng dylib vào file IPA
        await m.edit("Đang tiến hành tiêm tệp của bạn, xin chờ...")
        intermediate_file_path = original_file_path  # Bắt đầu với file gốc

        for iap_path in [ADBLOCK_PATH, SATELLA_PATH]:
            temp_output_path = intermediate_file_path.replace(".ipa", f"_temp_{os.path.basename(iap_path)}.ipa")
            temp_files.append(temp_output_path)  # Lưu lại đường dẫn tệp tạm

            command = f'/root/.local/bin/cyan -o {temp_output_path} -uwsgf {iap_path} -i {intermediate_file_path}'
            result = subprocess.run(
                ['sh', '-c', command],
                cwd=GETINSTALL_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy()
            )

            if result.returncode != 0:
                await m.edit(f"Đã xảy ra lỗi khi tiêm {iap_path}. Vui lòng liên hệ @dabeecao để báo lỗi.")
                return

            intermediate_file_path = temp_output_path  # Cập nhật file IPA tạm thời mới cho lần tiếp theo

        # Đổi tên file cuối cùng
        os.rename(intermediate_file_path, output_file_path)
        await m.edit("Tệp của bạn đã được tiêm thành công. Đang gửi lại tệp, xin chờ...")

        # Gửi tệp đã ký lên Telegram
        await message.reply_document(
            document=output_file_path,
            file_name=signed_file_name,
            caption=f"Đã tiêm thành công {media.file_name} thành {signed_file_name}\n\nNhấn /donate cho tiến sĩ nếu bạn thấy hữu ích nhé."
        )

        # Xoá tin nhắn thông báo
        await m.delete()

    except Exception as e:
        await m.edit(f"Đã xảy ra lỗi khi tiêm. Vui lòng liên hệ @dabeecao để báo lỗi.\nChi tiết lỗi: {str(e)}")
    finally:
        # Xóa các file tạm trong trường hợp có lỗi xảy ra
        for path in [original_file_path, output_file_path] + temp_files:
            if os.path.exists(path):
                os.remove(path)
        
@app.on_message(filters.command(["inject_fix"], COMMAND_HANDLER))
async def inject_fix_handler(bot, message):
    # Kiểm tra nếu tin nhắn không phải là trong nhóm
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply("Lệnh này chỉ hỗ trợ trong nhóm. Hãy tham gia nhóm @thuthuatjb_sp để sử dụng.")

    # Kiểm tra nếu người dùng trả lời tin nhắn có file đính kèm
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("Vui lòng trả lời tập tin .ipa hoặc .tipa bằng lệnh.")

    media = message.reply_to_message.document
    if not media.file_name.endswith(('.ipa', '.tipa')):
        return await message.reply("Chỉ hỗ trợ tệp .ipa hoặc .tipa.")
    
    # Kiểm tra kích thước tập tin
    file_size_mb = media.file_size / (1024 * 1024)  # Kích thước tập tin tính bằng MB
    if file_size_mb > MAX_FILE_SIZE_MB:
        return await message.reply("Tệp quá lớn. Vui lòng chỉ tải lên các tập tin dưới 1GB.")

    # Kiểm tra sự tồn tại của các tệp và đường dẫn cần thiết
    required_files = {
        "FIX": FIX_PATH,
        "FIX1": FIX1_PATH,
        "FIX2": FIX2_PATH,
    }
    for name, path in required_files.items():
        if not os.path.exists(path):
            return await message.reply(f"Tệp {name} không tồn tại: {path}")

    # Tải file xuống
    m = await message.reply("Đang tải tập tin của bạn xuống máy chủ xử lý...")
    now = time.time()
    dc_id = FileId.decode(media.file_id).dc_id
    original_file_path = await message.reply_to_message.download(
        file_name=os.path.join(ASSETS_DIR, generate_random_filename()),
        progress=progress_for_pyrogram,
        progress_args=("Đang cố tải về, xin chờ..", m, now, dc_id),
    )

    original_file_name = media.file_name  # Lưu lại tên tệp gốc
    
    # Đổi tên file thành .ipa nếu cần
    if original_file_path.endswith('.tipa'):
        new_file_path = original_file_path.replace('.tipa', '.ipa')
        os.rename(original_file_path, new_file_path)
        original_file_path = new_file_path

    output_file_path = original_file_path.replace(".ipa", "_output.ipa")
    signed_file_name = f"{os.path.basename(original_file_name).replace('.ipa', '')}_fixsideload_TTJB.ipa"
    temp_files = []  # Danh sách để lưu các tệp tạm

    try:
        # Tiêm từng dylib vào file IPA
        await m.edit("Đang tiến hành tiêm tệp của bạn, xin chờ...")
        intermediate_file_path = original_file_path  # Bắt đầu với file gốc

        for fix_path in [FIX_PATH, FIX1_PATH, FIX2_PATH]:
            temp_output_path = intermediate_file_path.replace(".ipa", f"_temp_{os.path.basename(fix_path)}.ipa")
            temp_files.append(temp_output_path)  # Lưu lại đường dẫn tệp tạm

            command = f'/root/.local/bin/cyan -o {temp_output_path} -uwsgf {fix_path} -i {intermediate_file_path}'
            result = subprocess.run(
                ['sh', '-c', command],
                cwd=GETINSTALL_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy()
            )

            if result.returncode != 0:
                await m.edit(f"Đã xảy ra lỗi khi tiêm {fix_path}. Vui lòng liên hệ @dabeecao để báo lỗi.")
                return

            intermediate_file_path = temp_output_path  # Cập nhật file IPA tạm thời mới cho lần tiếp theo

        # Đổi tên file cuối cùng
        os.rename(intermediate_file_path, output_file_path)
        await m.edit("Tệp của bạn đã được tiêm thành công. Đang gửi lại tệp, xin chờ...")

        # Gửi tệp đã ký lên Telegram
        await message.reply_document(
            document=output_file_path,
            file_name=signed_file_name,
            caption=f"Đã tiêm thành công {media.file_name} thành {signed_file_name}\n\nNhấn /donate cho tiến sĩ nếu bạn thấy hữu ích nhé."
        )

        # Xoá tin nhắn thông báo
        await m.delete()

    except Exception as e:
        await m.edit(f"Đã xảy ra lỗi khi tiêm. Vui lòng liên hệ @dabeecao để báo lỗi.\nChi tiết lỗi: {str(e)}")
    finally:
        # Xóa các file tạm trong trường hợp có lỗi xảy ra
        for path in [original_file_path, output_file_path] + temp_files:
            if os.path.exists(path):
                os.remove(path)
                

@app.on_message(filters.command(["inject_ext"], COMMAND_HANDLER))
async def inject_ext_handler(bot, message):
    # Kiểm tra nếu tin nhắn không phải là trong nhóm
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply("Lệnh này chỉ hỗ trợ trong nhóm. Hãy tham gia nhóm @thuthuatjb_sp để sử dụng.")

    # Kiểm tra nếu người dùng trả lời tin nhắn có file đính kèm
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("Vui lòng trả lời tập tin .ipa hoặc .tipa bằng lệnh.")

    media = message.reply_to_message.document
    if not media.file_name.endswith(('.ipa', '.tipa')):
        return await message.reply("Chỉ hỗ trợ tệp .ipa hoặc .tipa.")

    # Kiểm tra kích thước tập tin
    file_size_mb = media.file_size / (1024 * 1024)  # Kích thước tập tin tính bằng MB
    if file_size_mb > MAX_FILE_SIZE_MB:
        return await message.reply("Tệp quá lớn. Vui lòng chỉ tải lên các tập tin dưới 1GB.")

    # Kiểm tra sự tồn tại của dylib
    if not os.path.exists(EXTENSIONFIX_PATH):
        return await message.reply(f"Tệp EXTENSIONFIX không tồn tại: {EXTENSIONFIX_PATH}")

    # Tải file xuống
    m = await message.reply("Đang tải tập tin của bạn xuống máy chủ xử lý...")
    now = time.time()
    dc_id = FileId.decode(media.file_id).dc_id
    original_file_path = await message.reply_to_message.download(
        file_name=os.path.join(ASSETS_DIR, generate_random_filename()),
        progress=progress_for_pyrogram,
        progress_args=("Đang cố tải về, xin chờ..", m, now, dc_id),
    )

    original_file_name = media.file_name  # Lưu lại tên tệp gốc

    # Đổi tên file thành .ipa nếu cần
    if original_file_path.endswith('.tipa'):
        new_file_path = original_file_path.replace('.tipa', '.ipa')
        os.rename(original_file_path, new_file_path)
        original_file_path = new_file_path

    signed_file_name = f"{os.path.basename(original_file_name).replace('.ipa', '')}_fixEXT_TTJB.ipa"
    output_file_path = os.path.join(ASSETS_DIR, signed_file_name)

    try:
        # Chạy lệnh ipapatch
        await m.edit("Đang tiêm ExtensionFix vào IPA...")
        command = [
            'ipapatch',
            '--input', original_file_path,
            '--output', output_file_path,
            '--dylib', EXTENSIONFIX_PATH,
            '--noconfirm'
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Không xác định được lỗi."
            return await m.edit(f"Đã xảy ra lỗi khi tiêm IPA.\nChi tiết lỗi: {error_msg}")

        await m.edit("Tệp của bạn đã được tiêm thành công. Đang gửi lại tệp, xin chờ...")

        # Gửi tệp đã ký lên Telegram
        await message.reply_document(
            document=output_file_path,
            file_name=signed_file_name,
            caption=f"Đã tiêm thành công {media.file_name} thành {signed_file_name}\n\nNhấn /donate cho tiến sĩ nếu bạn thấy hữu ích nhé."
        )

        # Xoá tin nhắn thông báo
        await m.delete()

    except Exception as e:
        await m.edit(f"Đã xảy ra lỗi khi tiêm. Vui lòng liên hệ @dabeecao để báo lỗi.\nChi tiết lỗi: {str(e)}")
    finally:
        # Xóa các file tạm
        for path in [original_file_path, output_file_path]:
            if os.path.exists(path):
                os.remove(path)
        
@app.on_message(filters.command(["getfile"], COMMAND_HANDLER) & filters.user(SUDO))
@capture_err
@new_task
async def download(client, message):
    pesan = await message.reply_text(f"{E_LOADING} Đang xử lý...", quote=True)
    if message.reply_to_message is not None:
        # Trường hợp trả lời vào một tệp
        start_t = datetime.now()
        c_time = time.time()
        reply = message.reply_to_message
        media = reply.document or reply.video or reply.audio
        if not media and reply.photo:
            media = reply.photo[-1]
        if not media:
            return await pesan.edit(f"{E_ERROR} Loại phương tiện không được hỗ trợ.")
        dc_id = FileId.decode(media.file_id).dc_id

        random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        base_name = getattr(media, "file_name", None) or f"file_{random_suffix}"
        name, ext = os.path.splitext(base_name)
        if not ext and reply.photo:
            ext = ".jpg"
        download_path = f'/opt/storage/Private/Downloads/{name}_{random_suffix}{ext}'

        the_real_download_location = await client.download_media(
            message=message.reply_to_message,
            file_name=download_path,
            progress=progress_for_pyrogram,
            progress_args=("Đang cố tải về, xin chờ..", pesan, c_time, dc_id),
        )
        end_t = datetime.now()
        ms = (end_t - start_t).seconds
        file_size = os.path.getsize(the_real_download_location)
        file_name = getattr(media, "file_name", None) or os.path.basename(the_real_download_location) or "file"
        await pesan.edit(
            f"{E_SUCCESS} Đã tải tệp tin đến máy chủ lưu trữ.\nTên tệp tin: <code>{file_name}</code>\nKích thước <code>{file_size}</code> bytes\nĐã tải trong <u>{ms}</u> giây.",
            parse_mode=enums.ParseMode.HTML,
        )
    elif len(message.command) > 1:
        # Trường hợp tải file từ URL
        start_t = datetime.now()
        the_url_parts = " ".join(message.command[1:])
        url = the_url_parts.strip()
        custom_file_name = os.path.basename(url)
        if "|" in the_url_parts:
            url, custom_file_name = the_url_parts.split("|")
            url = url.strip()
            custom_file_name = custom_file_name.strip()

        # Tạo chuỗi ngẫu nhiên để thêm vào tên tệp tải về từ URL
        random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        download_file_path = os.path.join("downloads/", os.path.splitext(custom_file_name)[0] + "_" + random_suffix + os.path.splitext(custom_file_name)[1])

        # Bắt đầu tải về
        downloader = SmartDL(url, download_file_path, progress_bar=False, timeout=10)
        try:
            downloader.start(blocking=False)
        except Exception as err:
            return await pesan.edit(str(err))

        # Hiển thị tiến trình tải về
        c_time = time.time()
        display_message = ""
        while not downloader.isFinished():
            total_length = downloader.filesize or None
            downloaded = downloader.get_dl_size(human=True)
            now = time.time()
            diff = now - c_time
            percentage = downloader.get_progress() * 100
            speed = downloader.get_speed(human=True)
            progress_str = "[{0}{1}]\nTiến trình: {2}%".format(
                "".join(["●" for _ in range(math.floor(percentage / 5))]),
                "".join(["○" for _ in range(20 - math.floor(percentage / 5))]),
                round(percentage, 2),
            )

            estimated_total_time = downloader.get_eta(human=True)
            try:
                current_message = (
                    f"Đang cố tải về...\nURL: <code>{url}</code>\n"
                    f"Tên tệp tin: <code>{unquote(custom_file_name)}</code>\n"
                    f"Tốc độ: {speed}\n{progress_str}\n"
                    f"{downloaded} of {humanbytes(total_length)}\n"
                    f"Hoàn thành sau: {estimated_total_time}"
                )
                if round(diff % 10.00) == 0 and current_message != display_message:
                    await pesan.edit(
                        text=current_message,
                        disable_web_page_preview=True,
                        parse_mode=enums.ParseMode.HTML,
                    )
                    display_message = current_message
                    await asyncio.sleep(10)
            except Exception as e:
                LOGGER.info(str(e))
        
        # Tải lên Telegram và xoá file
        if os.path.exists(download_file_path):
            await client.send_document(
                message.chat.id, download_file_path
            )
            
            # Lấy kích thước tệp tính bằng bytes
            file_size = os.path.getsize(download_file_path)
            
            os.remove(download_file_path)  # Xóa file sau khi tải lên

            end_t = datetime.now()
            ms = (end_t - start_t).seconds

            await pesan.edit(
                f"{E_SUCCESS} Đã tải xuống và tải lên Telegram <code>{download_file_path}</code> có kích thước {file_size} bytes trong {ms} giây",
                parse_mode=enums.ParseMode.HTML,
            )
    else:
        await pesan.edit(
            f"{E_ERROR} Trả lời Telegram Media hoặc gửi kèm URL để tải.",
            parse_mode=enums.ParseMode.HTML,
        )


@app.on_message(filters.command(["getinstall"], COMMAND_HANDLER))
@capture_err
@new_task
async def getinstall(_, message):
    await message.reply(
        f"Chứng chỉ thu hồi rồi, chờ chứng chỉ mới đi đồng chí.👌"
    )