import json
import os
import traceback
import logging
from logging import getLogger
from re import I
from re import split as ngesplit
from time import time
from urllib.parse import unquote

from pyrogram import Client, filters
from pyrogram.types import Message

from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.helper.human_read import get_readable_time
from tiensiteo.helper.localization import use_chat_lang
from tiensiteo.helper.pyro_progress import progress_for_pyrogram
from tiensiteo.helper.tools import get_random_string
from tiensiteo.plugins.dev import shell_exec
from tiensiteo.vars import COMMAND_HANDLER

LOGGER = getLogger("TienSiTeo")


ARCH_EXT = (
    "mkv",
    "mp4",
    "mov",
    "wmv",
    "3gp",
    "mpg",
    "webm",
    "avi",
    "flv",
    "m4v",
)

__MODULE__ = "TríchXuấtMedia"
__HELP__ = """
<blockquote>/toaudio [URL/Trả lời video] - Trích xuất tất cả các âm thanh từ video.
/tovoice [Trả lời âm thanh] - Chuyển các tệp âm thanh thành định dạng Voice</blockquote>
"""


def get_base_name(orig_path: str):
    if ext := [ext for ext in ARCH_EXT if orig_path.lower().endswith(ext)]:
        ext = ext[0]
        return ngesplit(f"{ext}$", orig_path, maxsplit=1, flags=I)[0]


def get_audio_name(lang, url, ext, stream_index):
    fragment_removed = url.split("#")[0]  # keep to left of first #
    query_string_removed = fragment_removed.split("?")[0]
    scheme_removed = query_string_removed.split("://")[-1].split(":")[-1]
    base_name = get_base_name(os.path.basename(unquote(scheme_removed)))
    
    # Đặt tên tệp âm thanh với tên gốc và chỉ số luồng
    if base_name:
        return f"{base_name}_stream_{stream_index}.{ext}"
    else:
        return f"tiensiteoAudio{get_random_string(4)}_stream_{stream_index}.{ext}"


@app.on_message(filters.command(["toaudio"], COMMAND_HANDLER))
@use_chat_lang()
async def extract_media(self, ctx: Message, strings):
    # Gửi tin nhắn thông báo bot đang xử lý
    pesan = await ctx.reply_msg(strings("progress_str"), quote=True)

    # Kiểm tra nếu chỉ có một đối số trong lệnh hoặc không phải trả lời tin nhắn có video
    if len(ctx.command) == 1 and not ctx.reply_to_message:
        await pesan.delete_msg()  # Xóa tin nhắn thông báo đang xử lý nếu lệnh không hợp lệ
        return await ctx.reply_msg(
            strings("extr_help").format(cmd=ctx.command[0]), quote=True, del_in=5
        )

    # Nếu người dùng trả lời tin nhắn nhưng không phải video
    if ctx.reply_to_message and not ctx.reply_to_message.video:
        await pesan.delete_msg()  # Xóa tin nhắn thông báo đang xử lý nếu lệnh không hợp lệ
        return await ctx.reply_msg(
            strings("extr_help").format(cmd=ctx.command[0]), quote=True, del_in=5
        )

    # Nếu người dùng trả lời tin nhắn có video, tải xuống video và sử dụng tệp đó làm đầu vào
    if ctx.reply_to_message and ctx.reply_to_message.video:
        video = ctx.reply_to_message.video
        # Tải video xuống
        download_path = await ctx.reply_to_message.download()
        link = download_path  # Sử dụng đường dẫn tệp đã tải làm đầu vào
    else:
        # Ngược lại, sử dụng URL từ lệnh gốc
        link = ctx.command[1]

    start_time = time()
    try:
        # Sử dụng ffprobe để lấy chi tiết của video hoặc URL
        res = (
            await shell_exec(
                f"ffprobe -loglevel 0 -print_format json -show_format -show_streams {link}"
            )
        )[0]
        details = json.loads(res)

        # Lấy tất cả các luồng âm thanh và trích xuất
        for stream in details["streams"]:
            if stream["codec_type"] == "audio":
                stream_index = stream["index"]
                codec_name = stream["codec_name"]
                
                if codec_name == "aac":
                    ext = "aac"
                elif codec_name == "mp3":
                    ext = "mp3"
                elif codec_name == "eac3":
                    ext = "eac3"
                else:
                    ext = "m4a"  # Mặc định sử dụng m4a nếu không nhận diện được codec

                # Đặt tên tệp âm thanh
                audio_file_name = get_audio_name("audio", link, ext, stream_index)
                
                # Trích xuất âm thanh
                LOGGER.info(f"Extracting audio stream {stream_index} to {audio_file_name}")
                await shell_exec(f"ffmpeg -i '{link}' -map 0:{stream_index} -c copy '{audio_file_name}'")

                # Gửi tệp âm thanh trích xuất được
                c_time = time()
                await ctx.reply_document(
                    audio_file_name,
                    caption=strings("capt_extr").format(
                        nf=audio_file_name, bot=self.me.username, timelog=get_readable_time(time() - start_time)
                    ),
                    thumb="assets/thumb.jpg",
                    progress=progress_for_pyrogram,
                    progress_args=(strings("up_str"), pesan, c_time, self.me.dc_id),
                )
                
                # Dọn dẹp tệp sau khi gửi
                os.remove(audio_file_name)

        # Hoàn tất xử lý
        await pesan.delete_msg()

    except Exception as e:
        LOGGER.error(traceback.format_exc())
        await pesan.edit_msg(strings("fail_extr_media"))

    # Dọn dẹp tệp video đã tải xuống nếu có
    if ctx.reply_to_message and ctx.reply_to_message.video:
        try:
            os.remove(download_path)
        except:
            pass
						
@app.on_message(filters.command(["tovoice"], COMMAND_HANDLER))
@use_chat_lang()
async def convert_to_voice(self, ctx: Message, strings):
    # Gửi tin nhắn thông báo bot đang xử lý
    pesan = await ctx.reply_msg(strings("progress_str"), quote=True)

    # Kiểm tra nếu lệnh không được trả lời vào tin nhắn có tệp audio hoặc tệp document với định dạng âm thanh phổ biến
    if not ctx.reply_to_message or not (
        ctx.reply_to_message.audio or
        (ctx.reply_to_message.document and 
         ctx.reply_to_message.document.mime_type.startswith("audio/") or
         ctx.reply_to_message.document.file_name.endswith((".flac", ".aac", ".mp3", ".wav")))
    ):
        await pesan.delete_msg()
        return await ctx.reply_msg(
            "Vui lòng trả lời vào một tệp âm thanh để chuyển đổi thành voice", quote=True, del_in=5
        )

    # Tải xuống tệp âm thanh từ ctx.reply_to_message thay vì audio_message
    download_path = await ctx.reply_to_message.download()
    voice_file_name = download_path.rsplit(".", 1)[0] + ".ogg"  # Đổi đuôi tệp thành .ogg

    # Đổi tên tệp để có đuôi .ogg
    os.rename(download_path, voice_file_name)

    try:
        # Gửi voice message
        c_time = time()
        await ctx.reply_voice(
            voice_file_name,
            caption="Đây là file voice từ audio của bạn",
            progress=progress_for_pyrogram,
            progress_args=(strings("up_str"), pesan, c_time, self.me.dc_id),
        )

    except Exception as e:
        LOGGER.error(traceback.format_exc())
        await pesan.edit_msg("Đã xảy ra lỗi khi gửi tệp dưới dạng voice.")

    finally:
        # Dọn dẹp tệp sau khi gửi
        await pesan.delete_msg()
        os.remove(voice_file_name)
