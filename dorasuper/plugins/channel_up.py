import html
import io
import secrets
import time
from datetime import datetime

from pyrogram import enums, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors.exceptions.bad_request_400 import DocumentInvalid
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database.up_channel_db import (
    get_up_acl, get_up_channel, get_up_file, is_up_allowed,
    save_up_file, set_up_acl, set_up_channel,
)
from dorasuper import BOT_USERNAME, app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.emoji import (
    E_DART, E_DOWNLOAD, E_ERROR, E_FIRE, E_GEAR, E_GIFT, E_IOS, E_LINK, E_LOADING,
    E_LOCK, E_MENU, E_PARTY, E_PIN_LOC, E_ROCKET, E_SHIELD, E_SPARKLE,
    E_STAR, E_SUCCESS, E_TIP, E_TROPHY, E_USER, E_WARN,
)
from dorasuper.helper.fame import mention_user
from dorasuper.helper.html_entities import html_to_entities, strip_custom_emoji_entities
from dorasuper.helper.channel_up import (
    build_channel_caption,
    is_allowed_package,
    is_appstore_url,
    lookup_appstore,
    render_appstore_poster,
    split_features,
)
from dorasuper.vars import COMMAND_HANDLER, SUDO, UP_CHANNEL

__MODULE__ = "ĐăngKênh"
__HELP__ = f"""
Đăng một bài (ảnh + caption + nút tải) lên kênh Telegram. Người xem bấm nút để bot gửi file trong tin nhắn riêng.

Chỉ admin bot và những người được ThanhDora duyệt mới dùng được /up. Người khác gửi /up sẽ chờ duyệt.

<blockquote>/up – Trả lời file (hoặc gửi kèm lệnh) rồi làm theo hướng dẫn: dán link App Store, nhập chức năng, bot sẽ render ảnh và đăng lên kênh.
/up_channel [@kenh | -100...] – Đặt kênh đăng bài (chỉ admin bot).
/cancel – Hủy phiên /up đang nhập.</blockquote>
"""

_HANDLER_GROUP = -2
_SESSION_TTL = 15 * 60
_sessions = {}

_CAPTION_EMOJI = {
    "trophy": E_TROPHY,
    "sparkle": E_SPARKLE,
    "star": E_STAR,
    "ios": E_IOS,
    "user": E_USER,
    "link": E_LINK,
    "gift": E_GIFT,
    "shield": E_SHIELD,
    "gear": E_GEAR,
    "rocket": E_ROCKET,
    "lock": E_LOCK,
    "dart": E_DART,
    "pin": E_PIN_LOC,
    "crown": E_MENU,
    "fire": E_FIRE,
    "party": E_PARTY,
}


def _is_sudo(message: Message) -> bool:
    user = message.from_user
    return bool(user and user.id in SUDO)


def _is_sudo_id(user_id) -> bool:
    return bool(user_id and int(user_id) in SUDO)


async def _can_use_up(user_id) -> bool:
    if _is_sudo_id(user_id):
        return True
    return await is_up_allowed(user_id)


def _approval_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(f"{E_SUCCESS} Duyệt", callback_data=f"upacl_ok_{user_id}"),
            InlineKeyboardButton(f"{E_ERROR} Từ chối", callback_data=f"upacl_no_{user_id}"),
        ]]
    )


async def _notify_owners_for_access(message: Message) -> bool:
    user = message.from_user
    mention = mention_user(user)
    username = f"@{user.username}" if user.username else "không có"
    text = (
        f"{E_WARN} <b>Yêu cầu dùng /up</b>\n"
        f"{E_USER} {mention}\n"
        f"Username: {html.escape(username)}\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"Duyệt để người này được đăng bài lên kênh bằng /up."
    )
    sent = 0
    for owner_id in SUDO:
        try:
            await app.send_message(
                owner_id,
                text,
                parse_mode=enums.ParseMode.HTML,
                reply_markup=_approval_markup(user.id),
            )
            sent += 1
        except Exception:
            continue
    return sent > 0


async def _request_up_access(message: Message):
    user = message.from_user
    existing = await get_up_acl(user.id)
    if existing and existing.get("status") == "pending":
        await _reply_html(
            message,
            f"{E_LOADING} Yêu cầu của bạn đang chờ ThanhDora duyệt. Vui lòng đợi nhé.",
        )
        return
    await set_up_acl(
        user.id,
        "pending",
        name=user.first_name or "",
        username=user.username or "",
        requested_at=time.time(),
    )
    sent = await _notify_owners_for_access(message)
    if sent:
        await _reply_html(
            message,
            f"{E_LOADING} Đã gửi yêu cầu dùng /up. Vui lòng đợi ThanhDora duyệt.",
        )
        return
    await _reply_html(
        message,
        f"{E_ERROR} Không gửi được yêu cầu tới ThanhDora. Thử lại sau hoặc liên hệ trực tiếp nhé.",
    )


def _session_of(message: Message):
    user = message.from_user
    if not user:
        return None, None
    data = _sessions.get(user.id)
    if not data:
        return user.id, None
    if time.time() - data.get("started", 0) > _SESSION_TTL:
        _sessions.pop(user.id, None)
        return user.id, None
    return user.id, data


def _source_file_message(message: Message):
    reply = message.reply_to_message
    if reply and reply.document:
        return reply
    if message.document:
        return message
    return None


async def _reply_html(message: Message, text: str, **kwargs):
    kwargs.setdefault("parse_mode", enums.ParseMode.HTML)
    return await message.reply_text(text, **kwargs)


def _has_custom_emoji(msg: Message) -> bool:
    ents = (getattr(msg, "caption_entities", None) or getattr(msg, "entities", None) or [])
    return any(getattr(e, "type", None) == enums.MessageEntityType.CUSTOM_EMOJI for e in ents)


async def _apply_caption_html(message: Message, html_caption: str, reply_markup=None):
    """Gắn caption sau khi ảnh đã lên, cùng cách parse HTML với tin nhắn thường."""
    try:
        edited = await message.edit_caption(
            html_caption, parse_mode=enums.ParseMode.HTML, reply_markup=reply_markup
        )
        if edited and _has_custom_emoji(edited):
            return edited
        if edited:
            message = edited
    except Exception:
        pass
    text, entities = html_to_entities(html_caption)
    try:
        edited = await message.edit_caption(
            text, caption_entities=entities, reply_markup=reply_markup
        )
        if edited:
            return edited
    except Exception:
        pass
    return await message.edit_caption(
        text,
        caption_entities=strip_custom_emoji_entities(entities),
        reply_markup=reply_markup,
    )


async def _send_photo_html(chat_id, photo, html_caption: str, **kwargs):
    markup = kwargs.get("reply_markup")
    posted = None
    try:
        posted = await app.send_photo(
            chat_id, photo, caption=html_caption, parse_mode=enums.ParseMode.HTML, **kwargs
        )
        if posted and _has_custom_emoji(posted):
            return posted
    except Exception:
        posted = None
        if hasattr(photo, "seek"):
            try:
                photo.seek(0)
            except Exception:
                pass
    if posted is None:
        posted = await app.send_photo(chat_id, photo, **kwargs)
    try:
        return await _apply_caption_html(posted, html_caption, reply_markup=markup)
    except Exception:
        if posted:
            return posted
        raise


async def _reply_photo_html(message: Message, photo, html_caption: str, **kwargs):
    markup = kwargs.get("reply_markup")
    sent = None
    try:
        sent = await message.reply_photo(
            photo, caption=html_caption, parse_mode=enums.ParseMode.HTML, **kwargs
        )
        if sent and _has_custom_emoji(sent):
            return sent
    except Exception:
        sent = None
        if hasattr(photo, "seek"):
            try:
                photo.seek(0)
            except Exception:
                pass
    if sent is None:
        sent = await message.reply_photo(photo, **kwargs)
    return await _apply_caption_html(sent, html_caption, reply_markup=markup)


def _bot_username() -> str:
    return BOT_USERNAME or getattr(getattr(app, "me", None), "username", None) or ""


def _download_markup(token: str) -> InlineKeyboardMarkup:
    username = _bot_username()
    url = f"https://t.me/{username}?start=upfile_{token}"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"{E_DOWNLOAD} Tải file", url=url)]]
    )


async def _resolved_channel():
    saved = await get_up_channel()
    return saved if saved is not None else UP_CHANNEL


def _post_link(chat, message_id: int) -> str:
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    raw = str(chat.id)
    if raw.startswith("-100"):
        raw = raw[4:]
    return f"https://t.me/c/{raw}/{message_id}"


async def _ensure_can_post(channel_id):
    chat = await app.get_chat(channel_id)
    me = await app.get_chat_member(chat.id, "me")
    status = me.status
    if status == ChatMemberStatus.ADMINISTRATOR:
        privileges = me.privileges
        if chat.type == ChatType.CHANNEL and privileges and not privileges.can_post_messages:
            return chat, "Bot là admin kênh nhưng chưa được quyền đăng tin."
        return chat, None
    if status == ChatMemberStatus.OWNER:
        return chat, None
    return chat, "Bot cần là admin của kênh và có quyền đăng tin."


@app.on_message(filters.command(["up_channel"], COMMAND_HANDLER), group=_HANDLER_GROUP)
@capture_err
async def command_up_channel(_, message: Message):
    if not _is_sudo(message):
        await _reply_html(message, f"{E_WARN} Chỉ admin bot mới đặt được kênh đăng bài.")
        return
    args = message.text.split(maxsplit=1)
    target = args[1].strip() if len(args) > 1 else None
    if not target:
        if message.chat.type == ChatType.CHANNEL:
            target = message.chat.id
        else:
            await _reply_html(
                message,
                f"{E_TIP} Dùng <code>/up_channel @tenkenh</code> hoặc <code>/up_channel -100...</code> "
                f"để chọn kênh đăng bài.",
            )
            return
    try:
        chat, err = await _ensure_can_post(target)
    except Exception as e:
        await _reply_html(message, f"{E_ERROR} Không mở được kênh đó: {html.escape(str(e))}")
        return
    if err:
        await _reply_html(message, f"{E_ERROR} {html.escape(err)}")
        return
    await set_up_channel(chat.id)
    title = html.escape(chat.title or str(chat.id))
    await _reply_html(message, f"{E_SUCCESS} Đã đặt kênh đăng bài: <b>{title}</b> (<code>{chat.id}</code>).")


@app.on_message(filters.command(["up"], COMMAND_HANDLER), group=_HANDLER_GROUP)
@capture_err
async def command_up(_, message: Message):
    if not message.from_user:
        return
    if not await _can_use_up(message.from_user.id):
        await _request_up_access(message)
        return
    channel = await _resolved_channel()
    if not channel:
        await _reply_html(
            message,
            f"{E_WARN} Chưa chọn kênh đăng bài. Dùng <code>/up_channel @tenkenh</code> trước nhé.",
        )
        return
    file_msg = _source_file_message(message)
    if not file_msg or not file_msg.document:
        await _reply_html(
            message,
            f"{E_TIP} Hãy trả lời một file <b>ipa</b>, <b>deb</b>, <b>dylib</b>,... bằng lệnh <code>/up</code>.",
        )
        return
    filename = file_msg.document.file_name or ""
    if not is_allowed_package(filename):
        await _reply_html(
            message,
            f"{E_ERROR} File <code>{html.escape(filename or 'không tên')}</code> không phải ipa/deb/dylib "
            f"hoặc gói quen thuộc (zip, 7z, rar, tipa).",
        )
        return
    extra = message.text.split(maxsplit=1)
    preset_link = extra[1].strip() if len(extra) > 1 else ""
    uid = message.from_user.id
    _sessions[uid] = {
        "step": "link",
        "started": time.time(),
        "file_chat_id": file_msg.chat.id,
        "file_msg_id": file_msg.id,
        "file_id": file_msg.document.file_id,
        "filename": filename,
        "ask_chat_id": message.chat.id,
    }
    if preset_link:
        await _handle_link(message, preset_link)
        return
    await _reply_html(
        message,
        f"{E_LINK} Đã nhận file <code>{html.escape(filename)}</code>.\n"
        f"Hãy gửi link App Store của game này (hoặc <code>/cancel</code> để hủy).",
    )


@app.on_message(filters.command(["cancel", "huy"], COMMAND_HANDLER), group=_HANDLER_GROUP)
@capture_err
async def command_up_cancel(_, message: Message):
    uid, data = _session_of(message)
    if not data:
        return
    _sessions.pop(uid, None)
    await _reply_html(message, f"{E_SUCCESS} Đã hủy đăng bài.")


def _is_up_session_text(_, __, message: Message) -> bool:
    if not message or not message.from_user or not message.text:
        return False
    if message.text.startswith("/"):
        return False
    uid, data = _session_of(message)
    return bool(data)


@app.on_message(filters.create(_is_up_session_text) & filters.text, group=_HANDLER_GROUP)
@capture_err
async def channel_up_session(_, message: Message):
    uid, data = _session_of(message)
    if not data:
        return
    if not await _can_use_up(uid):
        _sessions.pop(uid, None)
        await _request_up_access(message)
        return
    step = data.get("step")
    if step == "link":
        await _handle_link(message, (message.text or "").strip())
    elif step == "features":
        await _handle_features(message, (message.text or "").strip())


async def _handle_link(message: Message, raw: str):
    uid, data = _session_of(message)
    if not data:
        await _reply_html(message, f"{E_WARN} Phiên /up đã hết hạn. Gửi lại <code>/up</code> giúp em.")
        return
    if not is_appstore_url(raw):
        await _reply_html(
            message,
            f"{E_ERROR} Đây chưa phải link App Store. Hãy gửi link dạng "
            f"<code>https://apps.apple.com/...</code>",
        )
        return
    status = await _reply_html(message, f"{E_LOADING} Đang lấy thông tin và render ảnh từ App Store...")
    info = await lookup_appstore(raw)
    if not info or not info.get("icon_bytes"):
        await status.edit(
            f"{E_ERROR} Không lấy được ảnh từ link này. Kiểm tra lại link App Store giúp em.",
            parse_mode=enums.ParseMode.HTML,
        )
        return
    name = info.get("track_name") or "Ứng dụng"
    try:
        poster = render_appstore_poster(info["icon_bytes"], title=name)
    except Exception:
        await status.edit(
            f"{E_ERROR} Render ảnh không thành công. Thử lại link khác giúp em.",
            parse_mode=enums.ParseMode.HTML,
        )
        return
    data.update(
        {
            "step": "features",
            "started": time.time(),
            "store_url": info.get("track_view_url") or raw,
            "name": name,
            "version": info.get("version") or "",
            "seller": info.get("seller_name") or "",
            "poster": poster,
        }
    )
    _sessions[uid] = data
    photo = io.BytesIO(poster)
    photo.name = "poster.jpg"
    caption = (
        f"{E_SUCCESS} Đây là ảnh sẽ gửi kèm bài đăng của <b>{html.escape(name)}</b>"
        f"{' — ' + html.escape(data['version']) if data.get('version') else ''}.\n"
        f"{E_TIP} Hãy nhập chức năng của game (mỗi ý một dòng). Gửi <code>/cancel</code> để hủy."
    )
    try:
        await _reply_photo_html(message, photo, caption)
        await status.delete()
    except Exception:
        await status.edit(caption, parse_mode=enums.ParseMode.HTML)


async def _handle_features(message: Message, raw: str):
    uid, data = _session_of(message)
    if not data:
        await _reply_html(message, f"{E_WARN} Phiên /up đã hết hạn. Gửi lại <code>/up</code> giúp em.")
        return
    features = split_features(raw)
    if not features:
        await _reply_html(message, f"{E_TIP} Hãy nhập ít nhất một chức năng, mỗi ý một dòng.")
        return
    channel = await _resolved_channel()
    if not channel:
        _sessions.pop(uid, None)
        await _reply_html(message, f"{E_WARN} Chưa chọn kênh đăng bài. Dùng <code>/up_channel @tenkenh</code> trước nhé.")
        return
    status = await _reply_html(message, f"{E_LOADING} Đang đăng bài lên kênh...")
    caption, _overflow = build_channel_caption(
        name=data.get("name") or "Ứng dụng",
        version=data.get("version") or "",
        seller=data.get("seller") or "",
        store_url=data.get("store_url") or "",
        features=features,
        filename=data.get("filename") or "",
        emojis=_CAPTION_EMOJI,
    )
    token = secrets.token_hex(8)
    try:
        chat, err = await _ensure_can_post(channel)
        if err:
            await status.edit(f"{E_ERROR} {html.escape(err)}", parse_mode=enums.ParseMode.HTML)
            return
        if not _bot_username():
            await status.edit(
                f"{E_ERROR} Chưa lấy được username của bot nên không tạo được nút tải file.",
                parse_mode=enums.ParseMode.HTML,
            )
            return
        await save_up_file(token, {
            "file_id": data.get("file_id"),
            "file_chat_id": data.get("file_chat_id"),
            "file_msg_id": data.get("file_msg_id"),
            "filename": data.get("filename") or "",
            "name": data.get("name") or "",
            "created_by": uid,
            "created_at": time.time(),
        })
        photo = io.BytesIO(data["poster"])
        photo.name = "poster.jpg"
        posted = await _send_photo_html(
            chat.id,
            photo,
            caption,
            reply_markup=_download_markup(token),
        )
    except Exception as e:
        await status.edit(
            f"{E_ERROR} Không đăng được bài: {html.escape(str(e))}",
            parse_mode=enums.ParseMode.HTML,
        )
        return
    _sessions.pop(uid, None)
    link = _post_link(chat, posted.id)
    when = datetime.now().strftime("%H:%M %d/%m/%Y")
    await status.edit(
        f"{E_SUCCESS} Đã đăng bài lên <b>{html.escape(chat.title or 'kênh')}</b> lúc {when}.\n"
        f"{E_LINK} <a href=\"{html.escape(link, quote=True)}\">Xem bài đăng</a>",
        parse_mode=enums.ParseMode.HTML,
    )


async def deliver_up_file(message: Message, payload: str):
    token = (payload or "").lower().strip()
    if token.startswith("upfile_"):
        token = token[len("upfile_"):]
    rec = await get_up_file(token)
    if not rec or not rec.get("file_id"):
        await _reply_html(
            message,
            f"{E_ERROR} Không tìm thấy file này hoặc bài đăng đã hết hiệu lực.",
        )
        return
    name = rec.get("name") or "File"
    filename = rec.get("filename") or ""
    caption = f"{E_SUCCESS} <b>{html.escape(name)}</b>"
    if filename:
        caption += f"\n{E_GEAR} <code>{html.escape(filename)}</code>"
    try:
        await app.send_document(
            message.chat.id,
            rec["file_id"],
            file_name=filename or None,
            caption=caption,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        try:
            if rec.get("file_chat_id") and rec.get("file_msg_id"):
                await app.copy_message(message.chat.id, rec["file_chat_id"], rec["file_msg_id"])
                return
        except Exception:
            pass
        await _reply_html(
            message,
            f"{E_ERROR} Không gửi được file: {html.escape(str(e))}",
        )


@app.on_message(filters.command("start", COMMAND_HANDLER) & filters.private, group=_HANDLER_GROUP)
@capture_err
async def start_upfile(_, message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return
    payload = parts[1].lower().strip()
    if not payload.startswith("upfile_"):
        return
    await deliver_up_file(message, payload)


@app.on_callback_query(filters.regex(r"^upacl_(ok|no)_(\d+)$"), group=_HANDLER_GROUP)
@capture_err
async def up_acl_decide(_, cq: CallbackQuery):
    if not cq.from_user or cq.from_user.id not in SUDO:
        await cq.answer("Chỉ ThanhDora mới duyệt được yêu cầu này.", show_alert=True)
        return
    match = cq.matches[0] if cq.matches else None
    if not match:
        await cq.answer()
        return
    action, target_id = match.group(1), int(match.group(2))
    rec = await get_up_acl(target_id)
    try:
        target = await app.get_users(target_id)
        mention = mention_user(target)
    except Exception:
        name = (rec or {}).get("name") or str(target_id)
        mention = f'<a href="tg://user?id={target_id}">{html.escape(str(name))}</a>'
    if action == "ok":
        await set_up_acl(target_id, "allowed", decided_at=time.time(), decided_by=cq.from_user.id)
        result = f"{E_SUCCESS} Đã duyệt {mention} dùng /up."
        user_text = (
            f"{E_SUCCESS} ThanhDora đã duyệt. Bạn có thể dùng <code>/up</code> "
            f"(trả lời file IPA, DEB, dylib,...) để đăng bài lên kênh."
        )
        answer = "Đã duyệt"
    else:
        await set_up_acl(target_id, "denied", decided_at=time.time(), decided_by=cq.from_user.id)
        result = f"{E_ERROR} Đã từ chối {mention} dùng /up."
        user_text = f"{E_ERROR} ThanhDora đã từ chối quyền dùng /up."
        answer = "Đã từ chối"
    try:
        await cq.edit_message_text(result, parse_mode=enums.ParseMode.HTML)
    except Exception:
        try:
            await cq.message.reply_text(result, parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
    await cq.answer(answer)
    try:
        await app.send_message(target_id, user_text, parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass
