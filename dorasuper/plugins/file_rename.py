# Đổi tên file trong chat riêng: prefix, suffix, caption, thumbnail, metadata.
# Chuyển thể từ ThanhDora/misyou_iBot (bỏ premium/force-sub/duyệt user).
import os
import time
import shutil
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.file_id import FileId
from pyrogram.types import (
    CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from database import rename_db
from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.emoji import (
    E_CHECK, E_CROSS, E_ERROR, E_GEAR, E_IMAGE, E_INFO, E_LOADING, E_NOTE,
    E_SUCCESS, E_TIP, E_UPLOAD, E_DOWNLOAD, E_WARN,
)
from dorasuper.helper.pyro_progress import humanbytes, progress_for_pyrogram
from dorasuper.helper.rename_utils import (
    MAX_RENAME_SIZE, add_prefix_suffix, change_metadata, convert_duration,
    ensure_extension, format_caption, probe, safe_filename,
    get_bundle_id_from_file, fetch_itunes_artwork, fetch_itunes_artwork_and_inject_ipa,
    fetch_itunes_track_name, fetch_itunes_version, sanitize_filename_for_app,
    prepare_thumb_rgb,
)
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")
HTML = enums.ParseMode.HTML
WORK_DIR = "downloads/rename"
GROUP = 7  # nhóm riêng, không chặn các handler khác

# (chat_id, prompt_msg_id) -> file message
_PENDING: dict = {}

__MODULE__ = "ĐổiTênFile"
__HELP__ = """<blockquote>Gửi tài liệu/video/audio vào chat riêng với bot rồi trả lời tin nhắn bot bằng tên mới.

/set_prefix [text] - Đặt tiền tố tên file
/see_prefix, /del_prefix - Xem / xoá tiền tố
/set_suffix [text] - Đặt hậu tố tên file
/see_suffix, /del_suffix - Xem / xoá hậu tố
/set_caption [text] - Caption riêng. Biến: {filename} {filesize} {duration} {gamename}
/see_caption (/view_caption), /del_caption (/delcaption, /delete_caption)
/set_thumb - Trả lời ảnh (hoặc gửi ảnh kèm caption /set_thumb) để đặt thumbnail
/view_thumb (/viewthumb), /del_thumb (/delthumb, /delete_thumb)
/metadata - Bật/tắt chèn metadata (ffmpeg)
/set_metadata [text] - Đặt metadata, ví dụ:
<code>--change-title Tên
--change-video-title Tên
--change-audio-title Tên
--change-subtitle-title Tên
--change-author Tên</code>

Khi đổi tên file <b>.ipa</b>/<b>.deb</b>, bot tự lấy ảnh từ Apple iTunes làm thumbnail (và chèn vào IPA nếu là .ipa).</blockquote>"""

PM = filters.private & filters.incoming


def _cmd(*names):
    return filters.command(list(names), COMMAND_HANDLER) & PM


def _arg(m: Message):
    text = m.text or m.caption or ""
    parts = text.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


# ---------- Prefix / Suffix ----------
async def _set_simple(m: Message, key: str, label: str, example: str):
    val = _arg(m)
    if not val:
        return await m.reply(f"{E_TIP} Dùng: <code>/set_{key} {example}</code>", parse_mode=HTML)
    await rename_db.set_field(m.from_user.id, key, val)
    await m.reply(f"{E_SUCCESS} Đã lưu {label}: <code>{val}</code>", parse_mode=HTML)


async def _see_simple(m: Message, key: str, label: str):
    val = await rename_db.get_field(m.from_user.id, key)
    if val:
        await m.reply(f"{E_NOTE} {label.capitalize()} hiện tại:\n<code>{val}</code>", parse_mode=HTML)
    else:
        await m.reply(f"{E_INFO} Bạn chưa đặt {label}.", parse_mode=HTML)


async def _del_simple(m: Message, key: str, label: str):
    if not await rename_db.get_field(m.from_user.id, key):
        return await m.reply(f"{E_INFO} Bạn chưa đặt {label}.", parse_mode=HTML)
    await rename_db.del_field(m.from_user.id, key)
    await m.reply(f"{E_SUCCESS} Đã xoá {label}.", parse_mode=HTML)


@app.on_message(_cmd("set_prefix"), group=GROUP)
@capture_err
async def set_prefix(_, m: Message):
    await _set_simple(m, "prefix", "tiền tố", "[Dora]")


@app.on_message(_cmd("see_prefix"), group=GROUP)
@capture_err
async def see_prefix(_, m: Message):
    await _see_simple(m, "prefix", "tiền tố")


@app.on_message(_cmd("del_prefix"), group=GROUP)
@capture_err
async def del_prefix(_, m: Message):
    await _del_simple(m, "prefix", "tiền tố")


@app.on_message(_cmd("set_suffix"), group=GROUP)
@capture_err
async def set_suffix(_, m: Message):
    await _set_simple(m, "suffix", "hậu tố", "1080p")


@app.on_message(_cmd("see_suffix"), group=GROUP)
@capture_err
async def see_suffix(_, m: Message):
    await _see_simple(m, "suffix", "hậu tố")


@app.on_message(_cmd("del_suffix"), group=GROUP)
@capture_err
async def del_suffix(_, m: Message):
    await _del_simple(m, "suffix", "hậu tố")


# ---------- Caption ----------
@app.on_message(_cmd("set_caption"), group=GROUP)
@capture_err
async def set_caption(_, m: Message):
    val = _arg(m)
    if not val:
        return await m.reply(
            f"{E_TIP} Dùng: <code>/set_caption {{filename}} | {{filesize}} | {{duration}} | {{gamename}}</code>",
            parse_mode=HTML,
        )
    await rename_db.set_field(m.from_user.id, "caption", val)
    await m.reply(f"{E_SUCCESS} Đã lưu caption.", parse_mode=HTML)


@app.on_message(_cmd("see_caption", "view_caption"), group=GROUP)
@capture_err
async def see_caption(_, m: Message):
    await _see_simple(m, "caption", "caption")


@app.on_message(_cmd("del_caption", "delcaption", "delete_caption"), group=GROUP)
@capture_err
async def del_caption(_, m: Message):
    await _del_simple(m, "caption", "caption")


# ---------- Thumbnail ----------
@app.on_message(_cmd("set_thumb", "setthumb"), group=GROUP)
@capture_err
async def set_thumb(_, m: Message):
    src = m if m.photo else (m.reply_to_message if m.reply_to_message and m.reply_to_message.photo else None)
    if not src:
        return await m.reply(
            f"{E_TIP} Trả lời một ảnh bằng <code>/set_thumb</code>, hoặc gửi ảnh kèm caption <code>/set_thumb</code>.",
            parse_mode=HTML,
        )
    await rename_db.set_field(m.from_user.id, "thumb", src.photo.file_id)
    await m.reply(f"{E_SUCCESS} Đã lưu thumbnail.", parse_mode=HTML)


@app.on_message(_cmd("view_thumb", "viewthumb"), group=GROUP)
@capture_err
async def view_thumb(c, m: Message):
    thumb = await rename_db.get_field(m.from_user.id, "thumb")
    if not thumb:
        return await m.reply(f"{E_INFO} Bạn chưa đặt thumbnail.", parse_mode=HTML)
    await c.send_photo(m.chat.id, thumb, caption=f"{E_IMAGE} Thumbnail hiện tại", parse_mode=HTML)


@app.on_message(_cmd("del_thumb", "delthumb", "delete_thumb"), group=GROUP)
@capture_err
async def del_thumb(_, m: Message):
    await _del_simple(m, "thumb", "thumbnail")


# ---------- Metadata ----------
def _meta_kb(on: bool):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{E_CHECK} Metadata: BẬT" if on else f"{E_CROSS} Metadata: TẮT",
                              callback_data="rnmeta_toggle")],
        [InlineKeyboardButton(f"{E_GEAR} Đặt metadata riêng", callback_data="rnmeta_custom")],
    ])


async def _meta_text(uid):
    s = await rename_db.get_settings(uid)
    code = s.get("metadata_code") or rename_db.DEFAULT_METADATA
    state = "BẬT" if s.get("metadata") else "TẮT"
    return f"{E_GEAR} <b>Metadata:</b> {state}\n\n{E_NOTE} Metadata hiện tại:\n<code>{code}</code>", bool(s.get("metadata"))


@app.on_message(_cmd("metadata"), group=GROUP)
@capture_err
async def metadata_cmd(_, m: Message):
    text, on = await _meta_text(m.from_user.id)
    await m.reply(text, reply_markup=_meta_kb(on), parse_mode=HTML)


@app.on_message(_cmd("set_metadata"), group=GROUP)
@capture_err
async def set_metadata(_, m: Message):
    val = _arg(m)
    if not val:
        return await m.reply(
            f"{E_TIP} Dùng:\n<code>/set_metadata --change-title Tên\n--change-author Tên</code>",
            parse_mode=HTML,
        )
    await rename_db.set_field(m.from_user.id, "metadata_code", val)
    await m.reply(f"{E_SUCCESS} Đã lưu metadata. Bật/tắt bằng /metadata.", parse_mode=HTML)


@app.on_callback_query(filters.regex(r"^rnmeta_"))
async def metadata_cb(_, q: CallbackQuery):
    uid = q.from_user.id
    if q.data == "rnmeta_toggle":
        on = bool(await rename_db.get_field(uid, "metadata"))
        await rename_db.set_field(uid, "metadata", not on)
        text, on = await _meta_text(uid)
        await q.message.edit(text, reply_markup=_meta_kb(on), parse_mode=HTML)
        await q.answer("Đã đổi trạng thái metadata")
    else:
        await q.answer()
        await q.message.reply(
            f"{E_TIP} Gửi lệnh:\n<code>/set_metadata --change-title Tên\n--change-video-title Tên\n"
            f"--change-audio-title Tên\n--change-subtitle-title Tên\n--change-author Tên</code>",
            parse_mode=HTML,
        )


# ---------- Rename flow ----------
@app.on_message(PM & (filters.document | filters.video | filters.audio), group=GROUP)
@capture_err
async def rename_start(_, m: Message):
    if not m.from_user or (m.caption or "").startswith(tuple(COMMAND_HANDLER)):
        return
    media = getattr(m, m.media.value)
    if (media.file_size or 0) > MAX_RENAME_SIZE:
        return await m.reply(f"{E_WARN} Bot chỉ hỗ trợ file tối đa 2GB.", parse_mode=HTML)
    name = media.file_name or "không tên"
    prompt = await m.reply(
        f"{E_INFO} <b>Thông tin file</b>\n"
        f"• Tên cũ: <code>{name}</code>\n"
        f"• Dung lượng: <code>{humanbytes(media.file_size or 0)}</code>\n"
        f"• Loại: <code>{media.mime_type or '?'}</code>\n\n"
        f"{E_NOTE} Trả lời tin này bằng <b>tên mới</b> (có hoặc không đuôi file).",
        reply_markup=ForceReply(True, placeholder="Tên file mới"),
        parse_mode=HTML,
    )
    _PENDING[(m.chat.id, prompt.id)] = m
    if len(_PENDING) > 500:
        _PENDING.pop(next(iter(_PENDING)))


def _is_pending(_, __, m: Message):
    r = m.reply_to_message
    return bool(r and (m.chat.id, r.id) in _PENDING)


@app.on_message(PM & filters.text & filters.reply & filters.create(_is_pending), group=GROUP)
@capture_err
async def rename_reply(c, m: Message):
    file_msg = _PENDING.pop((m.chat.id, m.reply_to_message.id))
    media = getattr(file_msg, file_msg.media.value)
    for msg in (m, m.reply_to_message):
        try:
            await msg.delete()
        except Exception:
            pass
    await process_rename(c, file_msg, media, m.text)


def _shrink_thumb(path: str):
    """Chuẩn hoá thumbnail JPEG ≤ ~200KB, 320x320."""
    if not path or not os.path.exists(path):
        return None
    try:
        from PIL import Image
        img = prepare_thumb_rgb(Image.open(path))
        img = img.resize((320, 320), getattr(Image, "LANCZOS", Image.BICUBIC))
        # luôn lưu .jpg để Telegram nhận thumb ổn định
        out = path if path.lower().endswith((".jpg", ".jpeg")) else (os.path.splitext(path)[0] + ".jpg")
        for q in (85, 70, 55, 40, 30, 20):
            img.save(out, "JPEG", quality=q, optimize=True)
            if os.path.getsize(out) <= 200 * 1024:
                break
        return out
    except Exception as e:
        LOGGER.warning("rename thumb shrink error: %s", e)
        return None


async def process_rename(c, file_msg: Message, media, raw_name: str):
    uid = file_msg.from_user.id
    s = await rename_db.get_settings(uid)
    new_name = ensure_extension(raw_name, media.file_name or "")
    new_name = safe_filename(add_prefix_suffix(new_name, s.get("prefix"), s.get("suffix")))
    work = os.path.join(WORK_DIR, f"{uid}_{file_msg.id}_{int(time.time())}")
    os.makedirs(work, exist_ok=True)
    status = await file_msg.reply(f"{E_LOADING} Đang xử lý...", parse_mode=HTML)
    try:
        try:
            src_dc = FileId.decode(media.file_id).dc_id
        except Exception:
            src_dc = "-"
        start = time.time()
        path = await c.download_media(
            file_msg, file_name=os.path.join(work, new_name),
            progress=progress_for_pyrogram,
            progress_args=(f"{E_DOWNLOAD} Đang tải xuống...", status, start, src_dc),
        )
        upload_path = path
        if s.get("metadata"):
            await status.edit(f"{E_GEAR} Đang chèn metadata...", parse_mode=HTML)
            out = os.path.join(work, "meta", new_name)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            if await change_metadata(path, out, s.get("metadata_code") or rename_db.DEFAULT_METADATA):
                upload_path = out
            else:
                await status.edit(f"{E_WARN} Không chèn được metadata, gửi file gốc...", parse_mode=HTML)

        # --- Apple iTunes artwork cho .ipa / .deb ---
        orig_name = (media.file_name or "").strip()
        orig_low = orig_name.lower()
        new_low = (new_name or "").lower()
        is_ipa = orig_low.endswith(".ipa") or new_low.endswith(".ipa")
        is_deb = orig_low.endswith(".deb") or new_low.endswith(".deb")
        is_ipa_deb = is_ipa or is_deb
        itunes_thumb = None
        itunes_track_name = None
        bundle_id = app_name = version = None

        if is_ipa_deb:
            await status.edit(f"{E_LOADING} Đang giải nén file, tìm Bundle ID...", parse_mode=HTML)
            ext_hint = orig_name if (orig_low.endswith(".ipa") or orig_low.endswith(".deb")) else new_name
            bundle_id, app_name, version = get_bundle_id_from_file(upload_path, extension_hint=ext_hint)
            if bundle_id:
                LOGGER.info(
                    "rename iTunes bundle_id=%s app=%s version=%s file=%s",
                    bundle_id, app_name or "", version or "", orig_name,
                )
                await status.edit(f"{E_LOADING} Đang lấy ảnh từ iTunes...", parse_mode=HTML)
                try:
                    if is_ipa:
                        modified_ipa, thumb_path, err = await fetch_itunes_artwork_and_inject_ipa(
                            bundle_id, upload_path, out_dir=work,
                        )
                        if modified_ipa:
                            upload_path = modified_ipa
                            LOGGER.info("Đã chèn iTunesArtwork vào IPA. bundle_id=%s", bundle_id)
                        if thumb_path:
                            itunes_thumb = thumb_path
                        elif err:
                            LOGGER.warning("iTunes inject IPA: %s", err)
                    if itunes_thumb is None:
                        itunes_path, err = await fetch_itunes_artwork(bundle_id, out_dir=work)
                        if itunes_path:
                            itunes_thumb = itunes_path
                        elif err:
                            LOGGER.warning("iTunes artwork: %s", err)
                except Exception as e:
                    LOGGER.warning("iTunes fetch error: %s", e, exc_info=True)
                try:
                    itunes_track_name = await fetch_itunes_track_name(bundle_id)
                except Exception:
                    itunes_track_name = None
            else:
                LOGGER.info("Không tìm thấy Bundle ID | file=%s", orig_name)

        info = await probe(upload_path)
        try:
            duration = int(float(info.get("format", {}).get("duration", 0)))
        except (TypeError, ValueError):
            duration = 0

        # Caption: {gamename} + style AppName cho ipa/deb
        caption = format_caption(
            s.get("caption"), new_name, humanbytes(media.file_size or 0),
            convert_duration(duration), gamename=itunes_track_name or "",
        )
        if is_ipa_deb and bundle_id and (app_name or version or bundle_id):
            itunes_version = None
            if not version:
                try:
                    itunes_version = await fetch_itunes_version(bundle_id)
                except Exception:
                    itunes_version = None
            app_name_val = itunes_track_name or app_name or "N/A"
            app_version_val = version or itunes_version or "N/A"
            caption = (
                f"<b>Tên app</b> : {app_name_val}" + chr(10)
                + f"<b>Phiên bản</b> : {app_version_val}" + chr(10)
                + f"<b>Bundle ID</b> : {bundle_id}"
            )
        elif itunes_track_name and not s.get("caption"):
            caption = f"<b>{itunes_track_name}</b>" + chr(10) + caption

        # Đổi tên upload theo track name iTunes (giữ prefix/suffix) khi có
        upload_name = new_name
        if itunes_track_name and is_ipa_deb:
            safe_name = sanitize_filename_for_app(itunes_track_name)
            ext = os.path.splitext(upload_path)[1] or (".ipa" if is_ipa else ".deb")
            upload_name = safe_filename(
                add_prefix_suffix(f"{safe_name}{ext}", s.get("prefix"), s.get("suffix"))
            )

        # Thumbnail: ưu tiên ảnh iTunes nếu lấy được; không thì thumb user / file
        thumb = None
        if itunes_thumb:
            thumb = _shrink_thumb(itunes_thumb)
        if thumb is None:
            tid = s.get("thumb") or (media.thumbs[0].file_id if getattr(media, "thumbs", None) else None)
            if tid:
                try:
                    user_thumb = await c.download_media(tid, file_name=os.path.join(work, "thumb.jpg"))
                    thumb = _shrink_thumb(user_thumb)
                except Exception as e:
                    LOGGER.warning("rename thumb error: %s", e)
                    thumb = None

        start = time.time()
        await c.send_document(
            file_msg.chat.id, upload_path, file_name=upload_name, thumb=thumb, caption=caption,
            parse_mode=HTML, reply_to_message_id=file_msg.id,
            progress=progress_for_pyrogram,
            progress_args=(f"{E_UPLOAD} Đang tải lên...", status, start, src_dc),
        )
        await status.delete()
    except Exception as e:
        LOGGER.error("rename error: %s", e, exc_info=True)
        try:
            await status.edit(f"{E_ERROR} Lỗi khi đổi tên: <code>{e}</code>", parse_mode=HTML)
        except Exception:
            pass
    finally:
        shutil.rmtree(work, ignore_errors=True)
