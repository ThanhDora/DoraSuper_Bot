import io
import subprocess
import time
import logging
from logging import getLogger
from os import path
from os import remove as osremove

from pyrogram import filters
from pyrogram.file_id import FileId
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from dorasuper import app
from dorasuper.helper import post_to_telegraph, progress_for_pyrogram, runcmd
from dorasuper.helper.emoji_fmt import EMOJI_FMT, EMOJI_FMT_BTN
from dorasuper.helper.localization import use_chat_lang
from dorasuper.helper.mediainfo_paste import mediainfo_paste
from dorasuper.vars import COMMAND_HANDLER, THUMB_PATH
from utils import get_file_id

LOGGER = getLogger("DoraSuper")

@app.on_message(filters.command(["mediainfo"], COMMAND_HANDLER))
@use_chat_lang()
async def mediainfo(_, ctx: Message, strings):
    if ctx.reply_to_message and ctx.reply_to_message.media:
        process = await ctx.reply_msg(strings("processing_text").format(**EMOJI_FMT), quote=True)
        file_info = get_file_id(ctx.reply_to_message)
        if file_info is None:
            return await process.edit_msg(strings("media_invalid").format(**EMOJI_FMT))
        if (
            ctx.reply_to_message.video
            and ctx.reply_to_message.video.file_size > 2097152000
        ) or (
            ctx.reply_to_message.document
            and ctx.reply_to_message.document.file_size > 2097152000
        ):
            return await process.edit_msg(strings("dl_limit_exceeded").format(**EMOJI_FMT), del_in=6)
        c_time = time.time()
        dc_id = FileId.decode(file_info.file_id).dc_id
        try:
            dl = await ctx.reply_to_message.download(
                file_name="downloads/",
                progress=progress_for_pyrogram,
                progress_args=(strings("dl_args_text").format(**EMOJI_FMT), process, c_time, dc_id),
            )
        except FileNotFoundError:
            return await process.edit_msg("ERROR: FileNotFound.")
        file_path = path.join("downloads/", path.basename(dl))
        output_ = await runcmd(f'mediainfo "{file_path}"')
        out = output_[0] if len(output_) != 0 else None
        body_text = f"""
DoraSuper MediaInfo
JSON
{file_info}.type
    
DETAILS
{out or 'Not Supported'}
    """
        try:
            link = await mediainfo_paste(out, "DoraSuper Mediainfo")
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(text=strings("viweb").format(**EMOJI_FMT_BTN).strip(), url=link)]]
            )
        except:
            try:
                link = await post_to_telegraph(
                    False, "DoraSuper MediaInfo", f"<code>{body_text}</code>"
                )
                markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(text=strings("viweb").format(**EMOJI_FMT_BTN).strip(), url=link)]]
                )
            except:
                markup = None
        with io.BytesIO(str.encode(body_text)) as out_file:
            out_file.name = "DoraSuper_Mediainfo.txt"
            await ctx.reply_document(
                out_file,
                caption=strings("capt_media").format(
                    ment=ctx.from_user.mention
                    if ctx.from_user
                    else ctx.sender_chat.title,
                    **EMOJI_FMT,
                ),
                thumb=THUMB_PATH,
                reply_markup=markup,
            )
            await process.delete()
        try:
            osremove(file_path)
        except Exception:
            pass
    else:
        try:
            link = ctx.input
            process = await ctx.reply_msg(strings("wait_msg").format(**EMOJI_FMT))
            try:
                output = subprocess.check_output(["mediainfo", f"{link}"]).decode(
                    "utf-8"
                )
            except Exception:
                return await process.edit_msg(strings("err_link").format(**EMOJI_FMT))
            body_text = f"""
            DoraSuperBot MediaInfo
            {output}
            """
            # link = await post_to_telegraph(False, title, body_text)
            try:
                link = await mediainfo_paste(out, "DoraSuper Mediainfo")
                markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(text=strings("viweb").format(**EMOJI_FMT_BTN).strip(), url=link)]]
                )
            except:
                try:
                    link = await post_to_telegraph(
                        False, "DoraSuper MediaInfo", body_text
                    )
                    markup = InlineKeyboardMarkup(
                        [[InlineKeyboardButton(text=strings("viweb").format(**EMOJI_FMT_BTN).strip(), url=link)]]
                    )
                except:
                    markup = None
            with io.BytesIO(str.encode(output)) as out_file:
                out_file.name = "DoraSuper_Mediainfo.txt"
                await ctx.reply_document(
                    out_file,
                    caption=strings("capt_media").format(
                        ment=ctx.from_user.mention
                        if ctx.from_user
                        else ctx.sender_chat.title
                    ),
                    thumb=THUMB_PATH,
                    reply_markup=markup,
                )
                await process.delete()
        except IndexError:
            return await ctx.reply_msg(
                strings("mediainfo_help").format(cmd=ctx.command[0], **EMOJI_FMT), del_in=6
            )
