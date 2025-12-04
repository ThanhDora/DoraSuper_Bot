import asyncio
import aiohttp
import os
import subprocess
import tempfile
import uuid
import logging
from logging import getLogger

from io import BytesIO
from uuid import uuid4
from httpx import AsyncClient, Timeout
from pyrogram import filters, enums
from pyrogram.types import Message
from tiensiteo import app

LOGGER = getLogger("TienSiTeo")

fetch = AsyncClient(
    http2=True,
    verify=False,
    headers={
        "Accept-Language": "en-US",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 Edge/107.0.1418.42",
    },
    timeout=Timeout(20),
)

class QuotlyException(Exception):
    pass

async def upload_to_catbox(file_path: str, client: app) -> str:
    """Upload a file to Catbox and return the URL."""
    try:
        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("reqtype", "fileupload")
                data.add_field("time", "1h")
                data.add_field("fileToUpload", f, filename=os.path.basename(file_path))
                
                async with session.post("https://litterbox.catbox.moe/resources/internals/api.php", data=data) as resp:
                    if resp.status == 200:
                        url = await resp.text()
                        return url
                    else:
                        LOGGER.error("Catbox upload failed: %s", resp.status)
                        return ""
    except Exception as e:
        LOGGER.error("Catbox upload error: %s", str(e))
        return ""

async def convert_media_to_image(input_path: str) -> str:
    """Convert any sticker, video, or GIF to static image using ffmpeg."""
    try:
        output_path = os.path.join(tempfile.gettempdir(), f"quotly_{uuid.uuid4()}.png")
        
        command = [
            'ffmpeg',
            '-y',
            '-i', input_path,
            '-vframes', '1',
            '-f', 'image2',
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            LOGGER.error(f"FFmpeg error: {stderr.decode()}")
            raise QuotlyException("Failed to convert media to image")
        
        if not os.path.exists(output_path):
            raise QuotlyException("Converted image not found")
        
        return output_path
    except Exception as e:
        LOGGER.error(f"Media conversion error: {str(e)}")
        if 'output_path' in locals() and os.path.exists(output_path):
            os.remove(output_path)
        raise QuotlyException(f"Media conversion failed: {str(e)}")

async def get_message_sender_info(message: Message) -> dict:
    """Extract sender information from a message."""
    sender = {
        "id": 1,
        "name": "",
        "username": "",
        "photo": None,
        "emoji_status": None,
        "type": "private"
    }

    if not message.chat:
        LOGGER.warning("Message has no chat: %s", message)
        return sender

    sender["type"] = message.chat.type.name.lower()

    if message.forward_date:
        if message.forward_sender_name:
            sender["name"] = message.forward_sender_name
        elif message.forward_from:
            sender.update({
                "id": message.forward_from.id,
                "name": f"{message.forward_from.first_name} {message.forward_from.last_name or ''}".strip(),
                "username": message.forward_from.username or "",
                "photo": {
                    "big_file_id": message.forward_from.photo.big_file_id
                } if message.forward_from.photo else None,
                "emoji_status": message.forward_from.emoji_status.custom_emoji_id if message.forward_from.emoji_status else None
            })
        elif message.forward_from_chat:
            sender.update({
                "id": message.forward_from_chat.id,
                "name": message.forward_from_chat.title,
                "username": message.forward_from_chat.username or "",
                "photo": {
                    "big_file_id": message.forward_from_chat.photo.big_file_id
                } if message.forward_from_chat.photo else None
            })
    elif message.from_user:
        sender.update({
            "id": message.from_user.id,
            "name": f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip(),
            "username": message.from_user.username or "",
            "photo": {
                "big_file_id": message.from_user.photo.big_file_id
            } if message.from_user.photo else None,
            "emoji_status": message.from_user.emoji_status.custom_emoji_id if message.from_user.emoji_status else None
        })
    elif message.sender_chat:
        sender.update({
            "id": message.sender_chat.id,
            "name": message.sender_chat.title,
            "username": message.sender_chat.username or "",
            "photo": {
                "big_file_id": message.sender_chat.photo.big_file_id
            } if message.sender_chat.photo else None
        })

    return sender

async def get_message_content(message: Message) -> tuple:
    """Extract text and entities from a message."""
    text = message.text or message.caption or ""
    entities = []

    for entity in (message.entities or message.caption_entities or []):
        entity_data = {
            "type": entity.type.name.lower(),
            "offset": entity.offset,
            "length": entity.length
        }
        if entity.type.name.lower() == "text_link":
            entity_data["url"] = entity.url
        elif entity.type.name.lower() == "custom_emoji":
            entity_data["custom_emoji_id"] = entity.custom_emoji_id
        entities.append(entity_data)

    return text, entities

async def get_media_info(message: Message, client: app) -> dict:
    """Extract media information from a message and upload to Catbox."""
    media_types = [message.sticker, message.photo, message.video, message.animation]
    media = next((m for m in media_types if m), None)
    
    if not media:
        return {}

    try:
        # Check file size before downloading
        file_size = getattr(media, 'file_size', None)
        max_size = 50 * 1024 * 1024  # 50 MB in bytes
        if file_size and file_size > max_size:
            LOGGER.warning(f"Media file size ({file_size} bytes) exceeds 50 MB limit")
            raise QuotlyException("Không hỗ trợ media lớn hơn 50MB")

        file_path = await client.download_media(media, in_memory=False)
        if not file_path:
            return {}

        final_path = file_path
        if message.sticker or message.video or message.animation:
            try:
                final_path = await convert_media_to_image(file_path)
            except QuotlyException as e:
                LOGGER.error("Media conversion skipped: %s", str(e))
                if os.path.exists(file_path):
                    os.remove(file_path)
                return {}
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        elif message.photo:
            final_path = file_path

        media_url = await upload_to_catbox(final_path, client)
        if not media_url:
            return {}

        width = getattr(media, 'width', 512)
        height = getattr(media, 'height', 512)

        if final_path != file_path and os.path.exists(final_path):
            os.remove(final_path)
        elif os.path.exists(file_path):
            os.remove(file_path)

        return {
            "media": {
                "url": media_url,
                "width": width,
                "height": height,
                "is_animated": False
            }
        }
    except Exception as e:
        LOGGER.error("Media processing error: %s", str(e))
        if 'final_path' in locals() and os.path.exists(final_path):
            os.remove(final_path)
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        raise  # Re-raise the exception to propagate to the caller

async def pyrogram_to_quotly(messages, is_reply: bool, client: app) -> bytes:
    """Convert Pyrogram messages to Quotly API payload."""
    if not isinstance(messages, list):
        messages = [messages]

    payload = {
        "type": "quote",
        "format": "png",
        "backgroundColor": "#1b1429",
        "width": 512,
        "height": 768,
        "scale": 2,
        "emojiBrand": "apple",
        "messages": []
    }

    for message in messages:
        sender = await get_message_sender_info(message)
        text, entities = await get_message_content(message)
        media_info = await get_media_info(message, client)

        message_data = {
            "from": {
                "id": sender["id"],
                "name": sender["name"],
                "username": sender["username"],
                "photo": sender["photo"],
                "emoji_status": sender["emoji_status"]
            },
            "text": text,
            "entities": entities,
            "avatar": bool(sender["photo"])
        }

        if media_info.get("media"):
            message_data.update(media_info)

        if is_reply and message.reply_to_message:
            reply_sender = await get_message_sender_info(message.reply_to_message)
            reply_text, reply_entities = await get_message_content(message.reply_to_message)
            message_data["replyMessage"] = {
                "name": reply_sender["name"],
                "text": reply_text,
                "entities": reply_entities,
                "chatId": reply_sender["id"],
                "from": {
                    "id": reply_sender["id"],
                    "name": reply_sender["name"],
                    "username": reply_sender["username"],
                    "photo": reply_sender["photo"]
                }
            }

        payload["messages"].append(message_data)

    response = await fetch.post("https://bot.lyo.su/quote/generate.png", json=payload)
    
    if response.is_error:
        error = response.json().get("error", response.text)
        raise QuotlyException(f"API Error: {error}")
    
    return response.content

def is_arg_int(text: str) -> tuple[bool, int]:
    """Check if argument is a valid integer."""
    try:
        return True, int(text)
    except ValueError:
        return False, 0

async def delete_after_delay(message: Message, seconds: int):
    """Delete a message after a specified delay."""
    await asyncio.sleep(seconds)
    await message.delete()

@app.on_message(filters.command(["q", "r"]) & filters.reply)
async def msg_quotly_cmd(client: app, message: Message):
    """Handle /q and /r commands to generate quote stickers."""
    if message.chat.type != enums.ChatType.GROUP and message.chat.type != enums.ChatType.SUPERGROUP:
        return await message.reply("Lệnh này chỉ hỗ trợ trong nhóm. Hãy tham gia nhóm ví dụ như @thuthuatjb_sp để sử dụng.")
    processing_msg = await message.reply_text("Đang xử lý...")
    
    try:
        is_reply = message.command[0].endswith("r")
        
        if message.command[0].startswith("q") and len(message.command) > 1:
            is_valid, count = is_arg_int(message.command[1])
            if is_valid:
                if count < 1 or count > 10:
                    await processing_msg.delete()
                    error_msg = await message.reply_text("Phạm vi không hợp lệ (1-10)")
                    asyncio.create_task(delete_after_delay(error_msg, 6))
                    return
                
                messages = [
                    msg for msg in await client.get_messages(
                        chat_id=message.chat.id,
                        message_ids=range(
                            message.reply_to_message.id,
                            message.reply_to_message.id + count
                        ),
                        replies=-1
                    ) if not msg.empty and (msg.text or msg.caption or msg.sticker or msg.photo or msg.video or msg.animation)
                ]
            else:
                await processing_msg.delete()
                error_msg = await message.reply_text("Đối số không hợp lệ")
                asyncio.create_task(delete_after_delay(error_msg, 6))
                return
        else:
            messages = [await client.get_messages(
                chat_id=message.chat.id,
                message_ids=message.reply_to_message.id,
                replies=-1
            )]

        if not messages:
            raise QuotlyException("Không tìm thấy tin nhắn hợp lệ")

        quote_image = await pyrogram_to_quotly(messages, is_reply, client)

        sticker = BytesIO(quote_image)
        sticker.name = f"quote_{uuid4()}.webp"
        
        await processing_msg.delete()
        await message.reply_sticker(sticker)

    except QuotlyException as e:
        await processing_msg.delete()
        error_msg = await message.reply_text(f"Lỗi: {str(e)}")
        asyncio.create_task(delete_after_delay(error_msg, 10))
    except Exception as e:
        await processing_msg.delete()
        error_msg = await message.reply_text(f"Đã xảy ra lỗi khi tạo sticker: {str(e)}")
        asyncio.create_task(delete_after_delay(error_msg, 10))