import asyncio
import os
import re
import shutil
import tempfile
import logging
from logging import getLogger
import uuid
import textwrap
from os import remove as hapus
from asyncio import gather
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from pyrogram import Client, emoji, enums, filters
from pyrogram.errors import BadRequest, PeerIdInvalid, StickersetInvalid
from pyrogram.file_id import FileId
from pyrogram.raw.functions.messages import GetStickerSet, SendMedia
from pyrogram.raw.functions.stickers import (
    AddStickerToSet,
    CreateStickerSet,
    RemoveStickerFromSet,
)
from pyrogram.raw.types import (
    DocumentAttributeFilename,
    InputDocument,
    InputMediaUploadedDocument,
    InputStickerSetItem,
    InputStickerSetShortName,
)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from dorasuper import app
from dorasuper.emoji import E_GROUP, E_LOADING, E_TIP
from dorasuper.helper import fetch, use_chat_lang
from dorasuper.helper.emoji_fmt import EMOJI_FMT
from dorasuper.core.decorator.errors import capture_err
from dorasuper.vars import COMMAND_HANDLER, LOG_CHANNEL

LOGGER = getLogger("DoraSuper")

__MODULE__ = "NhãnDán"
__HELP__ = """
<blockquote>/kang [Trả lời sticker] - Thêm sticker vào gói của bạn.
/unkang [Trả lời sticker] - Xóa sticker khỏi gói của bạn (Chỉ có thể xóa sticker được thêm bởi bot này.).
/laysticker - Chuyển đổi sticker thành ảnh.
/stickerid - Xem ID của sticker.
/taosticker [Trả lời ảnh/video/gif] [emoji] - Chuyển đổi ảnh, video, hoặc GIF thành sticker.
/mmf [Trả lời ảnh/video/gif/emoji] Tạo meme vui bằng cách chèn văn bản. Sử dụng dấu ; để phân tách văn bản trên và dưới.
/q [số] - Tạo quote dưới dạng Sticker từ tin nhắn (ví dụ: /q 3 để lấy 3 tin nhắn).
/r - Tạo quote với reply message.</blockquote>
"""

LOGGER = getLogger("DoraSuper")

# Kích thước tối đa của tệp (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes

async def check_file_size(file_path):
    """Kiểm tra kích thước tệp trước khi tải xuống."""
    try:
        file_size = os.path.getsize(file_path)
        return file_size <= MAX_FILE_SIZE
    except FileNotFoundError:
        LOGGER.error(f"File not found: {file_path}")
        return False

async def is_valid_image(file_path):
    """Kiểm tra xem file có phải là ảnh hợp lệ không."""
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True
    except UnidentifiedImageError:
        LOGGER.error(f"File is not a valid image: {file_path}")
        return False
    except Exception as e:
        LOGGER.error(f"Error checking image validity: {str(e)}")
        return False

async def get_middle_frame(input_path):
    """Lấy frame đầu tiên của video hoặc sticker động WebM."""
    output_path = os.path.join(tempfile.gettempdir(), f"memify_{uuid.uuid4()}.png")
    try:
        # Trích xuất frame đầu tiên
        command = [
            "ffmpeg", "-y", "-i", input_path, "-vframes", "1", output_path
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            LOGGER.error(f"FFmpeg failed: {stderr.decode('utf-8')}")
            return None
        if not os.path.exists(output_path):
            LOGGER.error(f"Output image {output_path} was not created")
            return None
        if not await is_valid_image(output_path):
            LOGGER.error(f"FFmpeg created invalid image: {output_path}")
            return None
        return output_path
    except Exception as e:
        LOGGER.error(f"Exception in get_middle_frame: {str(e)}")
        return None

async def add_text_to_video(input_path, text):
    """Ghi chữ lên video hoặc GIF."""
    output_path = os.path.join(tempfile.gettempdir(), f"memify_{uuid.uuid4()}.mp4")
    try:
        if ";" in text:
            upper_text, lower_text = text.split(";", 1)
        else:
            upper_text = text
            lower_text = ""

        filter_complex = []
        if upper_text:
            upper_text = upper_text.replace("'", r"\'").replace(":", r"\:")
            filter_complex.append(
                f"drawtext=fontfile=assets/Roboto-Bold.ttf:fontsize=50:fontcolor=white:borderw=3:bordercolor=black:"
                f"text='{upper_text}':x=(w-tw)/2:y=10"
            )
        if lower_text:
            lower_text = lower_text.replace("'", r"\'").replace(":", r"\:")
            filter_complex.append(
                f"drawtext=fontfile=assets/Roboto-Bold.ttf:fontsize=50:fontcolor=white:borderw=3:bordercolor=black:"
                f"text='{lower_text}':x=(w-tw)/2:y=h-th-20"
            )
        filter_str = ",".join(filter_complex) if filter_complex else "null"

        command = [
            "ffmpeg", "-y", "-i", input_path, "-vf", filter_str,
            "-c:v", "libx264", "-c:a", "copy", "-preset", "fast", output_path
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            LOGGER.error(f"FFmpeg failed: {stderr.decode('utf-8')}")
            return None
        if not os.path.exists(output_path):
            LOGGER.error(f"Output video {output_path} was not created")
            return None
        return output_path
    except Exception as e:
        LOGGER.error(f"Exception in add_text_to_video: {str(e)}")
        return None

async def draw_meme_text(image_path, text):
    """Tạo meme từ ảnh với văn bản."""
    try:
        if not os.path.exists(image_path):
            raise Exception(f"Image file does not exist: {image_path}")
        if not await is_valid_image(image_path):
            raise Exception(f"Cannot identify image file: {image_path}")

        img = Image.open(image_path)
        hapus(image_path)
        i_width, i_height = img.size
        m_font = ImageFont.truetype(
            "assets/Roboto-Bold.ttf", int((70 / 640) * i_width)
        )
        if ";" in text:
            upper_text, lower_text = text.split(";", 1)
        else:
            upper_text = text
            lower_text = ""
        draw = ImageDraw.Draw(img)
        current_h, pad = 10, 5
        if upper_text:
            for u_text in textwrap.wrap(upper_text, width=15):
                text_bbox = m_font.getbbox(u_text)
                (left, top, right, bottom) = text_bbox
                u_width = abs(right - left)
                u_height = abs(top - bottom)

                for offset_x, offset_y in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    draw.text(
                        xy=(((i_width - u_width) / 2) + offset_x, int((current_h / 640) * i_width) + offset_y),
                        text=u_text,
                        font=m_font,
                        fill=(0, 0, 0),
                        stroke_width=3,
                        stroke_fill="black",
                    )
                draw.text(
                    xy=((i_width - u_width) / 2, int((current_h / 640) * i_width)),
                    text=u_text,
                    font=m_font,
                    fill=(255, 255, 255),
                )
                current_h += u_height + pad
        if lower_text:
            for l_text in textwrap.wrap(lower_text, width=15):
                text_bbox = m_font.getbbox(l_text)
                (left, top, right, bottom) = text_bbox
                u_width = abs(right - left)
                u_height = abs(top - bottom)

                for offset_x, offset_y in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    draw.text(
                        xy=(
                            ((i_width - u_width) / 2) + offset_x,
                            i_height - u_height - int((20 / 500) * i_width) + offset_y,
                        ),
                        text=l_text,
                        font=m_font,
                        fill=(0, 0, 0),
                        stroke_width=3,
                        stroke_fill="black",
                    )
                draw.text(
                    xy=(
                        (i_width - u_width) / 2,
                        i_height - u_height - int((20 / 500) * i_width),
                    ),
                    text=l_text,
                    font=m_font,
                    fill=(255, 255, 255),
                )
                current_h += u_height + pad

        unique_id = str(uuid.uuid4())
        webp_file = os.path.join(tempfile.gettempdir(), f"dorasupermeme_{unique_id}.webp")
        png_file = os.path.join(tempfile.gettempdir(), f"dorasupermeme_{unique_id}.png")
        new_size = (512, 512)
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        img.save(png_file, "PNG")
        img.save(webp_file, "WebP", quality=95)
        img.close()
        if not os.path.exists(png_file):
            raise Exception(f"Failed to save PNG file: {png_file}")
        if not os.path.exists(webp_file):
            raise Exception(f"Failed to save WebP file: {webp_file}")
        return webp_file, png_file
    except Exception as e:
        LOGGER.error(f"Error in draw_meme_text: {str(e)}")
        raise

def get_emoji_regex():
    e_list = [
        getattr(emoji, e).encode("unicode-escape").decode("ASCII")
        for e in dir(emoji)
        if not e.startswith("_")
    ]
    e_sort = sorted([x for x in e_list if not x.startswith("*")], reverse=True)
    pattern_ = f"({'|'.join(e_sort)})"
    return re.compile(pattern_)

EMOJI_PATTERN = get_emoji_regex()
SUPPORTED_TYPES = ["jpeg", "png", "webp"]

def resize_image(filename: str) -> str:
    """Resize image to max 512x512 while maintaining aspect ratio."""
    im = Image.open(filename)
    maxsize = 512
    scale = maxsize / max(im.width, im.height)
    sizenew = (int(im.width * scale), int(im.height * scale))
    im = im.resize(sizenew, Image.LANCZOS)
    downpath, f_name = os.path.split(filename)
    png_image = os.path.join(downpath, f"{f_name.split('.', 1)[0]}.png")
    im.save(png_image, "PNG")
    if png_image != filename:
        os.remove(filename)
    return png_image

async def convert_video(filename: str) -> str:
    """Convert video/GIF to WebM sticker format."""
    downpath, f_name = os.path.split(filename)
    webm_video = os.path.join(downpath, f"{f_name.split('.', 1)[0]}.webm")
    cmd = [
        "ffmpeg",
        "-loglevel",
        "quiet",
        "-i",
        filename,
        "-t",
        "00:00:03",
        "-vf",
        "fps=30,scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2",
        "-c:v",
        "vp9",
        "-b:v",
        "500k",
        "-preset",
        "ultrafast",
        "-y",
        "-an",
        webm_video,
    ]

    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.communicate()

    if not os.path.exists(webm_video):
        return False
    if webm_video != filename:
        os.remove(filename)
    return webm_video

async def _del_user_cmd(client, chat_id, msg_id):
    try:
        await client.delete_messages(chat_id, msg_id)
    except Exception:
        pass

@app.on_message(filters.command(["mmf"], COMMAND_HANDLER))
@capture_err
async def memify(client, message):
    if message.chat.type != enums.ChatType.GROUP and message.chat.type != enums.ChatType.SUPERGROUP:
        await message.reply(f"{E_GROUP} Lệnh này chỉ hỗ trợ trong nhóm. Hãy tham gia nhóm ví dụ @thuthuatjb_sp để sử dụng.")
        await _del_user_cmd(client, message.chat.id, message.id)
        return
    rid = message.id
    if not message.reply_to_message:
        await message.reply_msg(
            "Vui lòng trả lời một sticker, ảnh hoặc video. Sử dụng dấu ; để phân tách văn bản trên và dưới.",
            reply_to_message_id=rid,
        )
        await _del_user_cmd(client, message.chat.id, message.id)
        return

    reply = message.reply_to_message
    if not (reply.sticker or reply.photo or reply.video or reply.animation or reply.document):
        await message.reply_msg(
            "Vui lòng reply đến một sticker, ảnh, video, sticker động hoặc GIF.",
            reply_to_message_id=rid,
        )
        await _del_user_cmd(client, message.chat.id, message.id)
        return

    if not message.text or len(message.text.split()) < 2:
        await message.reply_msg(
            "Vui lòng cung cấp văn bản cho meme, ví dụ: /mmf Văn bản trên;Văn bản dưới",
            reply_to_message_id=rid,
        )
        await _del_user_cmd(client, message.chat.id, message.id)
        return

    # Thông báo đang xử lý
    processing_msg = await message.reply_msg(f"{E_LOADING} Đang xử lý...", reply_to_message_id=rid)

    webp = None
    png = None
    file_path = None
    output_file = None
    try:
        unique_id = str(uuid.uuid4())
        file_path = await reply.download(file_name=os.path.join(tempfile.gettempdir(), f"temp_{unique_id}"))
        if not file_path:
            await processing_msg.edit(f"{E_ERROR} Không thể tải xuống tệp.")
            await _del_user_cmd(client, message.chat.id, message.id)
            return

        # Lấy thông tin mime_type và file_name
        mime_type = reply.sticker.mime_type if reply.sticker else None
        file_name = reply.sticker.file_name if reply.sticker else os.path.basename(file_path)

        if not await check_file_size(file_path):
            hapus(file_path)
            await processing_msg.edit(f"{E_ERROR} Tệp quá lớn! Kích thước tối đa là 50MB.")
            await _del_user_cmd(client, message.chat.id, message.id)
            return

        # Kiểm tra sticker động TGS
        is_tgs = mime_type == "application/x-tgsticker" or file_name.lower().endswith('.tgs')
        if is_tgs:
            hapus(file_path)
            await processing_msg.edit(f"{E_ERROR} Sticker động định dạng TGS không được hỗ trợ.")
            await _del_user_cmd(client, message.chat.id, message.id)
            return

        # Kiểm tra sticker động (WebM)
        is_webm = mime_type == "video/webm" or file_name.lower().endswith('.webm')

        if reply.video or reply.animation:
            output_file = await add_text_to_video(file_path, message.text.split(None, 1)[1].strip())
            if not output_file:
                hapus(file_path)
                await processing_msg.edit(f"{E_ERROR} Không thể xử lý video/GIF. Đảm bảo FFmpeg được cài đặt và file hợp lệ.")
                await _del_user_cmd(client, message.chat.id, message.id)
                return
            hapus(file_path)
            await processing_msg.delete()
            await message.reply_video(
                output_file,
                caption=f"{E_SUCCESS} Meme Video/GIF by DoraSuper",
                disable_notification=True,
                reply_to_message_id=rid,
            )
            await _del_user_cmd(client, message.chat.id, message.id)
        elif reply.sticker and (reply.sticker.is_animated or is_webm):
            temp_image = await get_middle_frame(file_path)
            if not temp_image:
                hapus(file_path)
                await processing_msg.edit(f"{E_ERROR} Không thể xử lý sticker động. Đảm bảo FFmpeg được cài đặt và file hợp lệ.")
                await _del_user_cmd(client, message.chat.id, message.id)
                return
            hapus(file_path)
            file_path = temp_image
            webp, png = await draw_meme_text(file_path, message.text.split(None, 1)[1].strip())
            await processing_msg.delete()
            await gather(
                message.reply_document(png, caption=f"{E_SUCCESS} Meme PNG by DoraSuper", reply_to_message_id=rid),
                message.reply_sticker(webp, emoji="😄", disable_notification=True, reply_to_message_id=rid)
            )
            await _del_user_cmd(client, message.chat.id, message.id)
        else:
            if not await is_valid_image(file_path):
                hapus(file_path)
                await processing_msg.edit(f"{E_ERROR} File tải xuống không phải ảnh hợp lệ.")
                await _del_user_cmd(client, message.chat.id, message.id)
                return
            webp, png = await draw_meme_text(file_path, message.text.split(None, 1)[1].strip())
            await processing_msg.delete()
            await gather(
                message.reply_document(png, caption=f"{E_SUCCESS} Meme PNG by DoraSuper", reply_to_message_id=rid),
                message.reply_sticker(webp, emoji="😄", disable_notification=True, reply_to_message_id=rid)
            )
            await _del_user_cmd(client, message.chat.id, message.id)

    except Exception as err:
        LOGGER.error(f"Error in memify: {str(err)}", exc_info=True)
        await processing_msg.edit(f"{E_ERROR} Lỗi: {str(err)}")
        await _del_user_cmd(client, message.chat.id, message.id)
    finally:
        for file in [webp, png, file_path, output_file]:
            try:
                if file and os.path.exists(file):
                    hapus(file)
            except:
                pass

@app.on_message(filters.command(["laysticker"], COMMAND_HANDLER), group=2)
@use_chat_lang()
async def getsticker_(self: Client, ctx: Message, strings):
    rid = ctx.id
    if not ctx.reply_to_message:
        await ctx.reply_msg(strings("not_sticker").format(**EMOJI_FMT), reply_to_message_id=rid)
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        return
    sticker = ctx.reply_to_message.sticker
    if not sticker:
        await ctx.reply_msg(f"{E_ERROR} Chỉ hỗ trợ sticker..", reply_to_message_id=rid)
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        return
    if sticker.is_animated:
        await ctx.reply_msg(strings("no_anim_stick").format(**EMOJI_FMT), reply_to_message_id=rid)
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        return
    with tempfile.TemporaryDirectory() as tempdir:
        path = os.path.join(tempdir, "getsticker")
        sticker_file = await self.download_media(
            message=ctx.reply_to_message,
            file_name=f"{path}/{sticker.set_name}.png",
        )
        await ctx.reply_document(
            document=sticker_file,
            caption=f"<b>Emoji:</b> {sticker.emoji}\n"
            f"<b>Sticker ID:</b> <code>{sticker.file_id}</code>\n\n"
            f"<b>Gửi bởi:</b> @{self.me.username}",
            reply_to_message_id=rid,
        )
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        shutil.rmtree(tempdir, ignore_errors=True)

@app.on_message(filters.command("stickerid", COMMAND_HANDLER) & filters.reply, group=2)
async def getstickerid(_, ctx: Message):
    if ctx.reply_to_message.sticker:
        await ctx.reply_msg(
            "ID của nhãn dán này là: <code>{stickerid}</code>".format(
                stickerid=ctx.reply_to_message.sticker.file_id
            ),
            reply_to_message_id=ctx.id,
        )
        await _del_user_cmd(app, ctx.chat.id, ctx.id)

@app.on_message(filters.command("unkang", COMMAND_HANDLER) & filters.reply, group=2)
@use_chat_lang()
async def unkangs(self: Client, ctx: Message, strings):
    rid = ctx.id
    if not ctx.from_user:
        await ctx.reply_msg(strings("unkang_anon").format(**EMOJI_FMT), reply_to_message_id=rid)
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        return
    if sticker := ctx.reply_to_message.sticker:
        if str(ctx.from_user.id) not in sticker.set_name:
            await ctx.reply_msg(strings("unkang_no").format(**EMOJI_FMT), reply_to_message_id=rid)
            await _del_user_cmd(self, ctx.chat.id, ctx.id)
            return
        pp = await ctx.reply_msg(strings("unkang_msg").format(**EMOJI_FMT), reply_to_message_id=rid)
        try:
            decoded = FileId.decode(sticker.file_id)
            sticker = InputDocument(
                id=decoded.media_id,
                access_hash=decoded.access_hash,
                file_reference=decoded.file_reference,
            )
            await app.invoke(RemoveStickerFromSet(sticker=sticker))
            await pp.edit_msg(strings("unkang_success").format(**EMOJI_FMT))
        except Exception as e:
            await pp.edit_msg(strings("unkang_error").format(e=e, **EMOJI_FMT))
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
    else:
        await ctx.reply_msg(strings("unkang_help").format(c=self.me.username, **EMOJI_FMT), del_in=6, reply_to_message_id=rid)
        await _del_user_cmd(self, ctx.chat.id, ctx.id)

@app.on_message(filters.command("kang", COMMAND_HANDLER), group=2)
@capture_err
@use_chat_lang()
async def kang_sticker(self: Client, ctx: Message, strings):
    rid = ctx.id
    if not ctx.from_user:
        await ctx.reply_msg(strings("anon_warn").format(**EMOJI_FMT), del_in=6, reply_to_message_id=rid)
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        return
    prog_msg = await ctx.reply_msg(strings("kang_msg").format(**EMOJI_FMT), reply_to_message_id=rid)
    sticker_emoji = "🤔"
    packnum = 0
    packname_found = False
    resize = False
    animated = False
    videos = False
    convert = False
    reply = ctx.reply_to_message
    user = await self.resolve_peer(ctx.from_user.username or ctx.from_user.id)

    if reply and reply.media:
        if reply.photo:
            resize = True
        elif reply.animation:
            videos = True
            convert = True
        elif reply.video:
            convert = True
            videos = True
        elif reply.document:
            if "image" in (reply.document.mime_type or ""):
                resize = True
            elif "video" in (reply.document.mime_type or "") or "gif" in (reply.document.mime_type or ""):
                videos = True
                convert = True
            elif "tgsticker" in (reply.document.mime_type or ""):
                animated = True
        elif reply.sticker:
            if not reply.sticker.file_name:
                await prog_msg.edit_msg(strings("stick_no_name").format(**EMOJI_FMT))
                await _del_user_cmd(self, ctx.chat.id, ctx.id)
                return
            if reply.sticker.emoji:
                sticker_emoji = reply.sticker.emoji
            animated = reply.sticker.is_animated
            videos = reply.sticker.is_video
            if videos:
                convert = False
            elif not reply.sticker.file_name.endswith(".tgs"):
                resize = True
        else:
            await prog_msg.edit_msg("Tôi không thể thêm kiểu sticker này.")
            await _del_user_cmd(self, ctx.chat.id, ctx.id)
            return

        pack_prefix = "anim" if animated else "vid" if videos else "a"
        packname = f"{pack_prefix}_{ctx.from_user.id}_by_{self.me.username}"

        if (
            len(ctx.command) > 1
            and ctx.command[1].isdigit()
            and int(ctx.command[1]) > 0
        ):
            packnum = int(ctx.command.pop(1))
            packname = (
                f"{pack_prefix}_{packnum}_{ctx.from_user.id}_by_{self.me.username}"
            )
        if len(ctx.command) > 1:
            sticker_emoji = (
                "".join(set(EMOJI_PATTERN.findall("".join(ctx.command[1:]))))
                or sticker_emoji
            )
        filename = await self.download_media(ctx.reply_to_message)
        if not filename:
            await prog_msg.delete()
            await _del_user_cmd(self, ctx.chat.id, ctx.id)
            return
    elif ctx.entities and len(ctx.entities) > 1:
        pack_prefix = "a"
        filename = "sticker.png"
        packname = f"c{ctx.from_user.id}_by_{self.me.username}"
        img_url = next(
            (
                ctx.text[y.offset : (y.offset + y.length)]
                for y in ctx.entities
                if y.type == "url"
            ),
            None,
        )

        if not img_url:
            await prog_msg.delete()
            await _del_user_cmd(self, ctx.chat.id, ctx.id)
            return
        try:
            r = await fetch.get(img_url)
            if r.status_code == 200:
                with open(filename, mode="wb") as f:
                    f.write(r.read())
        except Exception as r_e:
            await prog_msg.edit_msg(f"{r_e.__class__.__name__} : {r_e}")
            await _del_user_cmd(self, ctx.chat.id, ctx.id)
            return
        if len(ctx.command) > 2:
            if ctx.command[2].isdigit() and int(ctx.command[2]) > 0:
                packnum = int(ctx.command.pop(2))
                packname = f"a_{packnum}_{ctx.from_user.id}_by_{self.me.username}"
            if len(ctx.command) > 2:
                sticker_emoji = (
                    "".join(set(EMOJI_PATTERN.findall("".join(ctx.command[2:]))))
                    or sticker_emoji
                )
            resize = True
    else:
        await prog_msg.edit_msg(strings("kang_help").format(**EMOJI_FMT))
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        return
    try:
        if resize:
            filename = resize_image(filename)
        elif convert:
            filename = await convert_video(filename)
            if filename is False:
                await prog_msg.edit_msg("Error", del_in=6)
                await _del_user_cmd(self, ctx.chat.id, ctx.id)
                return
        max_stickers = 50 if animated else 120
        while not packname_found:
            try:
                stickerset = await self.invoke(
                    GetStickerSet(
                        stickerset=InputStickerSetShortName(short_name=packname),
                        hash=0,
                    )
                )
                if stickerset.set.count >= max_stickers:
                    packnum += 1
                    packname = f"{pack_prefix}_{packnum}_{ctx.from_user.id}_by_{self.me.username}"
                else:
                    packname_found = True
            except StickersetInvalid:
                break
        file = await self.save_file(filename)
        media = await self.invoke(
            SendMedia(
                peer=(await self.resolve_peer(LOG_CHANNEL)),
                media=InputMediaUploadedDocument(
                    file=file,
                    mime_type=self.guess_mime_type(filename),
                    attributes=[DocumentAttributeFilename(file_name=filename)],
                ),
                message="#Sticker kang",
                random_id=self.rnd_id(),
            ),
        )
        msg_ = media.updates[-1].message
        stkr_file = msg_.media.document
        if packname_found:
            await prog_msg.edit_msg(strings("exist_pack").format(**EMOJI_FMT))
            await self.invoke(
                AddStickerToSet(
                    stickerset=InputStickerSetShortName(short_name=packname),
                    sticker=InputStickerSetItem(
                        document=InputDocument(
                            id=stkr_file.id,
                            access_hash=stkr_file.access_hash,
                            file_reference=stkr_file.file_reference,
                        ),
                        emoji=sticker_emoji,
                    ),
                )
            )
        else:
            await prog_msg.edit_msg(strings("new_packs").format(**EMOJI_FMT))
            stkr_title = f"{ctx.from_user.first_name}'s "
            if animated:
                stkr_title += "AnimPack"
            elif videos:
                stkr_title += "VidPack"
            if packnum != 0:
                stkr_title += f" v{packnum}"
            try:
                await self.invoke(
                    CreateStickerSet(
                        user_id=user,
                        title=stkr_title,
                        short_name=packname,
                        stickers=[
                            InputStickerSetItem(
                                document=InputDocument(
                                    id=stkr_file.id,
                                    access_hash=stkr_file.access_hash,
                                    file_reference=stkr_file.file_reference,
                                ),
                                emoji=sticker_emoji,
                            )
                        ],
                    )
                )
            except PeerIdInvalid:
                await prog_msg.edit_msg(
                    strings("please_start_msg").format(**EMOJI_FMT),
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    strings("click_me").format(**EMOJI_FMT),
                                    url=f"https://t.me/{self.me.username}?start",
                                )
                            ]
                        ]
                    ),
                )
                await _del_user_cmd(self, ctx.chat.id, ctx.id)
                return

    except BadRequest:
        await prog_msg.edit_msg(strings("pack_full").format(**EMOJI_FMT))
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        return
    except Exception as all_e:
        LOGGER.exception("kang_sticker: %s", all_e)
        err_text = f"{all_e.__class__.__name__}: {str(all_e)}"[:250].replace("<", "").replace(">", "")
        try:
            await prog_msg.edit_msg(err_text)
        except Exception:
            pass
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
    else:
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text=strings("viewpack").format(**EMOJI_FMT),
                        url=f"https://t.me/addstickers/{packname}",
                    )
                ]
            ]
        )
        await prog_msg.edit_msg(
            strings("kang_success").format(emot=sticker_emoji, **EMOJI_FMT),
            reply_markup=markup,
        )
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        await self.delete_messages(
            chat_id=LOG_CHANNEL, message_ids=msg_.id, revoke=True
        )
        try:
            os.remove(filename)
        except OSError:
            pass

@app.on_message(filters.command("taosticker", COMMAND_HANDLER), group=2)
@use_chat_lang()
async def tosticker(self: Client, ctx: Message, strings):
    rid = ctx.id
    if not ctx.reply_to_message or not ctx.reply_to_message.media:
        await ctx.reply_msg(f"{E_TIP} Vui lòng trả lời một ảnh, video, hoặc GIF!", del_in=6, reply_to_message_id=rid)
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        return

    prog_msg = await ctx.reply_msg(f"{E_LOADING} Đang chuyển đổi thành sticker...", reply_to_message_id=rid)
    sticker_emoji = "🤔"
    resize = False
    convert = False
    reply = ctx.reply_to_message

    # Check for custom emoji in command
    if len(ctx.command) > 1:
        sticker_emoji = (
            "".join(set(EMOJI_PATTERN.findall("".join(ctx.command[1:]))))
            or sticker_emoji
        )

    # Determine media type
    if reply.photo or (reply.document and "image" in reply.document.mime_type):
        resize = True
    elif reply.video or reply.animation or (
        reply.document and reply.document.mime_type in (
            enums.MessageMediaType.VIDEO,
            enums.MessageMediaType.ANIMATION,
        )
    ):
        convert = True
    else:
        await prog_msg.edit_msg("Định dạng không hỗ trợ! Chỉ hỗ trợ ảnh, video, hoặc GIF.", del_in=6)
        await _del_user_cmd(self, ctx.chat.id, ctx.id)
        return

    # Download media
    with tempfile.TemporaryDirectory() as tempdir:
        filename = await self.download_media(
            message=reply,
            file_name=os.path.join(tempdir, "sticker_input")
        )
        if not filename:
            await prog_msg.edit_msg("Không thể tải xuống tệp!", del_in=6)
            await _del_user_cmd(self, ctx.chat.id, ctx.id)
            return

        try:
            # Process media
            if resize:
                filename = resize_image(filename)
            elif convert:
                filename = await convert_video(filename)
                if filename is False:
                    await prog_msg.edit_msg("Lỗi khi chuyển đổi video/GIF!", del_in=6)
                    await _del_user_cmd(self, ctx.chat.id, ctx.id)
                    return

            # Send sticker
            await ctx.reply_sticker(
                sticker=filename,
                emoji=sticker_emoji,
                reply_to_message_id=rid,
            )
            await prog_msg.delete()
            await _del_user_cmd(self, ctx.chat.id, ctx.id)

        except Exception as e:
            await prog_msg.edit_msg(f"Lỗi: {str(e)}", del_in=6)
            await _del_user_cmd(self, ctx.chat.id, ctx.id)
        finally:
            # Cleanup
            try:
                if os.path.exists(filename):
                    os.remove(filename)
            except OSError:
                pass