import html
import re
import io
import secrets
import time
from dorasuper.helper.timezone import (
    FMT_DM_HM,
    FMT_HM_DMY,
    format_ts_vn,
    format_vn,
    now_vn,
    utc_timestamp,
)

from pyrogram import enums, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors.exceptions.bad_request_400 import DocumentInvalid
from pyrogram.types import (
    CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from database.up_channel_db import (
    clear_leave_ban, get_leave_ban, get_up_acl, get_up_channel, get_up_file,
    get_up_promo_links, get_up_promo_targets, is_up_allowed, list_leave_bans,
    save_leave_ban, save_up_file, set_up_acl, set_up_channel,
    set_up_link_channel, set_up_link_group,
)
from dorasuper import BOT_USERNAME, app
from dorasuper.core.decorator.errors import capture_err
from logging import getLogger
from dorasuper.emoji import (
    E_ERROR, E_LINK, E_LOADING,
    E_SUCCESS, E_TIP, E_USER, E_WARN,
)
from dorasuper.helper.fame import mention_user
from dorasuper.helper.autodel import skip_autodel
from dorasuper.helper.html_entities import html_to_entities, strip_custom_emoji_entities
from dorasuper.helper.channel_up import (
    CHANNEL_BUTTON_TEXT,
    DOWNLOAD_BUTTON_TEXT,
    GROUP_BUTTON_TEXT,
    JOINED_BUTTON_TEXT,
    build_channel_caption,
    build_delivery_captions,
    build_join_gate_keyboard_botapi,
    build_upfile_url,
    is_allowed_package,
    is_appstore_url,
    lookup_appstore,
    evaluate_join_gate_decision,
    join_gate_block_kind,
    membership_check_result,
    membership_is_banned,
    membership_is_joined,
    normalize_stored_features,
    normalize_telegram_link,
    parse_promo_link_args,
    public_username_from_tme_url,
    render_appstore_poster,
    reply_markup_to_botapi,
    should_autoban_on_leave,
    should_clear_leave_ban_on_unban,
    split_features,
)
from dorasuper.vars import COMMAND_HANDLER, LOG_CHANNEL, SUDO, UP_CHANNEL

LOGGER = getLogger("DoraSuper")

__MODULE__ = "ĐăngKênh"
__HELP__ = f"""
Đăng một bài (ảnh + caption + nút tải) lên kênh Telegram. Người xem bấm nút để bot gửi file trong tin nhắn riêng.

Chỉ admin bot và những người được ThanhDora duyệt mới dùng được /up. Người khác gửi /up sẽ chờ duyệt.

<blockquote>/up – Trả lời file (hoặc gửi kèm lệnh) rồi làm theo hướng dẫn: dán link App Store, nhập chức năng, bot sẽ render ảnh và đăng lên kênh.
/up_channel [@kenh | -100...] – Đặt kênh đăng bài (chỉ admin bot).
/up_link_channel [@kenh | https://t.me/... | -100... | here] – Đặt nút + chat_id Kênh (off/xóa để gỡ). Bot cần admin có quyền ban.
/up_link_group [@nhom | https://t.me/... | -100... | here] – Đặt nút + chat_id Nhóm chat (off/xóa để gỡ).
/up_unban &lt;id|@user&gt; – Gỡ ban tự động (kênh + nhóm) cho người bị ban vì rời.
/up_banlist – Xem danh sách đã bị ban tự động vì rời kênh/nhóm.
/cancel – Hủy phiên /up đang nhập.

Tải file qua nút trên kênh: người dùng phải đang trong Kênh và Nhóm chat. Tự rời sẽ bị ban khỏi cả hai tới khi admin /up_unban.</blockquote>
"""

_HANDLER_GROUP = -2
_SESSION_TTL = 15 * 60
_sessions = {}
_nocheck_warned = set()

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
            with skip_autodel():
                await app.send_message(
                    owner_id,
                    text,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=_approval_markup(user.id),
                    no_autodel=True,
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
    with skip_autodel():
        return await message.reply_text(text, **kwargs)


def _has_custom_emoji(msg: Message) -> bool:
    ents = (getattr(msg, "caption_entities", None) or getattr(msg, "entities", None) or [])
    return any(getattr(e, "type", None) == enums.MessageEntityType.CUSTOM_EMOJI for e in ents)


async def _edit_caption_via_botapi(
    chat_id, message_id, html_caption: str, reply_markup=None,
) -> bool:
    """Gắn caption HTML (+ reply_markup) qua Bot API. Trả True khi edit ok."""
    token = getattr(app, "bot_token", None)
    if not token:
        return False
    try:
        import aiohttp
    except ImportError:
        return False
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": html_caption,
        "parse_mode": "HTML",
    }
    markup = reply_markup_to_botapi(reply_markup)
    if markup is not None:
        payload["reply_markup"] = markup
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"https://api.telegram.org/bot{token}/editMessageCaption",
                json=payload,
            ) as resp:
                data = await resp.json(content_type=None)
        return bool(data.get("ok"))
    except Exception:
        return False


def _html_without_unsupported_for_entities(html_caption: str) -> str:
    """html_to_entities không hiểu blockquote — gỡ thẻ để khỏi hiện chữ thô nếu phải fallback."""
    text = re.sub(r"</?blockquote\b[^>]*>", "", html_caption or "", flags=re.I)
    return text


async def _apply_caption_html(message: Message, html_caption: str, reply_markup=None):
    """Gắn caption HTML sau khi ảnh đã lên. Ưu tiên Bot API HTML (giữ blockquote expandable)."""
    chat_id = message.chat.id if message.chat else None
    if chat_id and await _edit_caption_via_botapi(
        chat_id, message.id, html_caption, reply_markup=reply_markup,
    ):
        try:
            refreshed = await app.get_messages(chat_id, message.id)
            if refreshed:
                return refreshed
        except Exception:
            return message
        return message
    try:
        edited = await message.edit_caption(
            html_caption, parse_mode=enums.ParseMode.HTML, reply_markup=reply_markup
        )
        if edited:
            return edited
    except Exception:
        pass
    # Fallback entity path không hỗ trợ blockquote — gỡ thẻ để khỏi lộ chữ <blockquote>.
    text, entities = html_to_entities(_html_without_unsupported_for_entities(html_caption))
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
        if sent:
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


async def _post_markup(token: str) -> InlineKeyboardMarkup:
    """Hàng 1: Tải file. Hàng 2: Kênh | Nhóm chat (nếu đã setup). Chữ nút plain text."""
    username = _bot_username()
    rows = [[InlineKeyboardButton(DOWNLOAD_BUTTON_TEXT, url=build_upfile_url(username, token))]]
    targets = await get_up_promo_targets()
    link_row = []
    if targets["channel"]["url"]:
        link_row.append(InlineKeyboardButton(CHANNEL_BUTTON_TEXT, url=targets["channel"]["url"]))
    if targets["group"]["url"]:
        link_row.append(InlineKeyboardButton(GROUP_BUTTON_TEXT, url=targets["group"]["url"]))
    if link_row:
        rows.append(link_row)
    return InlineKeyboardMarkup(rows)


def _join_gate_markup(token: str, channel_url, group_url) -> InlineKeyboardMarkup:
    kb = build_join_gate_keyboard_botapi(token, channel_url=channel_url, group_url=group_url)
    rows = []
    for row in kb["inline_keyboard"]:
        buttons = []
        for btn in row:
            if btn.get("url"):
                buttons.append(InlineKeyboardButton(btn["text"], url=btn["url"]))
            else:
                buttons.append(InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"]))
        rows.append(buttons)
    return InlineKeyboardMarkup(rows)


async def _log_up(text: str):
    LOGGER.info("%s", text)
    if not LOG_CHANNEL:
        return
    try:
        await app.send_message(LOG_CHANNEL, text, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        LOGGER.warning("up log send failed: %s", e)


async def _bot_rights_in_chat(chat_id):
    """Trả (ok, status_text, can_ban)."""
    try:
        me = await app.get_chat_member(chat_id, "me")
    except Exception as e:
        return False, f"không đọc được quyền bot ({e})", False
    status = me.status
    if status == ChatMemberStatus.OWNER:
        return True, "owner", True
    if status == ChatMemberStatus.ADMINISTRATOR:
        priv = me.privileges
        can_ban = bool(priv and getattr(priv, "can_restrict_members", False))
        return True, "admin", can_ban
    return False, str(getattr(status, "name", status)), False


async def _resolve_promo_chat(url=None, chat_id=None, here_chat=None):
    """Resolve chat object + url từ url/chat_id/here."""
    chat = None
    err = None
    if here_chat is not None:
        try:
            chat = await app.get_chat(here_chat)
        except Exception as e:
            return None, url, f"Không mở được chat hiện tại: {e}"
    elif chat_id is not None:
        try:
            chat = await app.get_chat(int(chat_id))
        except Exception as e:
            return None, url, f"Không mở được chat_id {chat_id}: {e}"
    if chat is None and url:
        # public @username / t.me/user
        target = url
        if "t.me/+" in url or "joinchat/" in url.lower():
            # invite — try get_chat(url) anyway; may fail
            target = url
        else:
            m = re.search(r"t\.me/([A-Za-z0-9_]+)", url)
            if m:
                target = m.group(1)
        try:
            chat = await app.get_chat(target)
        except Exception as e:
            err = f"Chưa resolve được chat từ link (cần thêm chat_id hoặc dùng here): {e}"
    final_url = url
    if chat is not None:
        if not final_url:
            if getattr(chat, "username", None):
                final_url = f"https://t.me/{chat.username}"
            elif getattr(chat, "invite_link", None):
                final_url = chat.invite_link
        return chat, final_url, err
    return None, final_url, err


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


async def _handle_promo_link_command(message: Message, kind: str):
    """kind: channel | group. Đặt / xem / xóa link + chat_id nút dưới bài /up."""
    if not _is_sudo(message):
        await _reply_html(message, f"{E_WARN} Chỉ admin bot mới đặt được link Kênh / Nhóm chat.")
        return
    args = (message.text or "").split(maxsplit=1)
    raw = args[1].strip() if len(args) > 1 else ""
    targets = await get_up_promo_targets()
    current = targets[kind]
    label = "Kênh" if kind == "channel" else "Nhóm chat"
    cmd = "/up_link_channel" if kind == "channel" else "/up_link_group"
    parsed = parse_promo_link_args(raw)

    if parsed["action"] == "show":
        if current["url"] or current["chat_id"]:
            await _reply_html(
                message,
                f"{E_TIP} Nút <b>{label}</b>:\n"
                f"Link: <code>{html.escape(current['url'] or '—')}</code>\n"
                f"chat_id: <code>{html.escape(str(current['chat_id'] or '—'))}</code>\n"
                f"Đổi bằng <code>{cmd} @ten</code> / <code>{cmd} here</code> / "
                f"<code>{cmd} https://t.me/+... -100...</code>; gỡ bằng <code>{cmd} off</code>.",
            )
        else:
            await _reply_html(
                message,
                f"{E_TIP} Chưa đặt nút <b>{label}</b>.\n"
                f"Dùng <code>{cmd} @ten</code>, <code>{cmd} here</code> (trong nhóm/kênh), "
                f"hoặc <code>{cmd} https://t.me/+invite -100id</code>.",
            )
        return

    if parsed["action"] == "clear":
        if kind == "channel":
            await set_up_link_channel(None)
        else:
            await set_up_link_group(None)
        await _reply_html(message, f"{E_SUCCESS} Đã gỡ nút <b>{label}</b> khỏi bài /up.")
        return

    if parsed["action"] == "invalid":
        await _reply_html(
            message,
            f"{E_ERROR} Không hiểu tham số. Thử <code>@ten</code>, <code>here</code>, "
            f"<code>-100...</code> hoặc invite kèm chat_id.",
        )
        return

    here_chat = None
    if parsed["action"] == "here":
        if message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
            here_chat = message.chat.id
        else:
            await _reply_html(
                message,
                f"{E_ERROR} Gửi <code>{cmd} here</code> ngay trong nhóm/kênh cần gắn.",
            )
            return

    chat, final_url, resolve_err = await _resolve_promo_chat(
        url=parsed.get("url"),
        chat_id=parsed.get("chat_id"),
        here_chat=here_chat,
    )
    if chat is None and not final_url:
        await _reply_html(
            message,
            f"{E_ERROR} {html.escape(resolve_err or 'Thiếu link hoặc chat_id.')}",
        )
        return
    if chat is None and final_url and parsed.get("chat_id") is None:
        # store URL only; warn
        if kind == "channel":
            await set_up_link_channel(final_url, None)
        else:
            await set_up_link_group(final_url, None)
        await _reply_html(
            message,
            f"{E_WARN} Đã lưu link <b>{label}</b>: <code>{html.escape(final_url)}</code>\n"
            f"Chưa có <code>chat_id</code> nên bot chưa kiểm tra join/ban được. "
            f"Thêm bằng <code>{cmd} {html.escape(final_url)} -100...</code> hoặc "
            f"<code>{cmd} here</code> trong chat đó.\n"
            f"{html.escape(resolve_err or '')}",
        )
        return
    if chat is None and parsed.get("chat_id") is not None and final_url:
        # keep url + raw chat_id even if get_chat failed
        cid = int(parsed["chat_id"])
        if kind == "channel":
            await set_up_link_channel(final_url, cid)
        else:
            await set_up_link_group(final_url, cid)
        await _reply_html(
            message,
            f"{E_WARN} Đã lưu link + chat_id <code>{cid}</code> nhưng bot chưa mở được chat "
            f"({html.escape(resolve_err or 'lỗi')}). Kiểm tra bot đã vào chat chưa.",
        )
        return
    if chat is None:
        await _reply_html(message, f"{E_ERROR} {html.escape(resolve_err or 'Không resolve được chat.')}")
        return

    if not final_url:
        await _reply_html(
            message,
            f"{E_ERROR} Có chat_id nhưng chưa có URL công khai. Gửi kèm link invite "
            f"<code>{cmd} https://t.me/+... {chat.id}</code>.",
        )
        return

    ok, status_txt, can_ban = await _bot_rights_in_chat(chat.id)
    if kind == "channel":
        await set_up_link_channel(final_url, chat.id)
    else:
        await set_up_link_group(final_url, chat.id)
    rights = (
        f"Bot: <b>{html.escape(status_txt)}</b>; quyền ban: "
        f"<b>{'có' if can_ban else 'không'}</b>"
    )
    if not ok or not can_ban:
        rights += (
            f"\n{E_WARN} Hãy cấp bot quyền admin (cấm thành viên) trong chat này "
            f"để kiểm tra join và tự ban khi rời."
        )
    title = html.escape(chat.title or str(chat.id))
    await _reply_html(
        message,
        f"{E_SUCCESS} Đã đặt nút <b>{label}</b>: <code>{html.escape(final_url)}</code>\n"
        f"Chat: <b>{title}</b> (<code>{chat.id}</code>)\n{rights}",
    )


@app.on_message(filters.command(["up_link_channel"], COMMAND_HANDLER), group=_HANDLER_GROUP)
@capture_err
async def command_up_link_channel(_, message: Message):
    await _handle_promo_link_command(message, "channel")


@app.on_message(filters.command(["up_link_group"], COMMAND_HANDLER), group=_HANDLER_GROUP)
@capture_err
async def command_up_link_group(_, message: Message):
    await _handle_promo_link_command(message, "group")


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
            "bundle_id": info.get("bundle_id") or "",
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
        bundle_id=data.get("bundle_id") or "",
        store_url=data.get("store_url") or "",
        features=features,
        filename=data.get("filename") or "",
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
            "version": data.get("version") or "",
            "bundle_id": data.get("bundle_id") or "",
            "store_url": data.get("store_url") or "",
            "features": list(features),
            "created_by": uid,
            "created_at": utc_timestamp(),
        })
        photo = io.BytesIO(data["poster"])
        photo.name = "poster.jpg"
        posted = await _send_photo_html(
            chat.id,
            photo,
            caption,
            reply_markup=await _post_markup(token),
        )
    except Exception as e:
        await status.edit(
            f"{E_ERROR} Không đăng được bài: {html.escape(str(e))}",
            parse_mode=enums.ParseMode.HTML,
        )
        return
    _sessions.pop(uid, None)
    link = _post_link(chat, posted.id)
    # VPS chạy UTC — luôn format Asia/Ho_Chi_Minh cho người dùng VN
    when = format_vn(now_vn(), FMT_HM_DMY)
    await status.edit(
        f"{E_SUCCESS} Đã đăng bài lên <b>{html.escape(chat.title or 'kênh')}</b> lúc {when}.\n"
        f"{E_LINK} <a href=\"{html.escape(link, quote=True)}\">Xem bài đăng</a>",
        parse_mode=enums.ParseMode.HTML,
    )


async def _send_html_text(chat_id, html_text: str):
    """Gửi tin nhắn HTML; gỡ blockquote trước khi fallback entity để khỏi lộ thẻ thô."""
    try:
        return await app.send_message(chat_id, html_text, parse_mode=enums.ParseMode.HTML)
    except Exception:
        text, entities = html_to_entities(_html_without_unsupported_for_entities(html_text))
        try:
            return await app.send_message(chat_id, text, entities=entities)
        except Exception:
            return await app.send_message(
                chat_id, text, entities=strip_custom_emoji_entities(entities),
            )


async def _send_document_html(
    chat_id, file_id, html_caption: str, file_name=None, reply_markup=None,
):
    """Gửi document kèm caption HTML (blockquote) + nút. Ưu tiên parse_mode, rồi Bot API edit."""
    try:
        return await app.send_document(
            chat_id,
            file_id,
            file_name=file_name or None,
            caption=html_caption,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=reply_markup,
        )
    except Exception:
        pass
    sent = await app.send_document(
        chat_id, file_id, file_name=file_name or None, reply_markup=reply_markup,
    )
    if await _edit_caption_via_botapi(
        chat_id, sent.id, html_caption, reply_markup=reply_markup,
    ):
        return sent
    text, entities = html_to_entities(_html_without_unsupported_for_entities(html_caption))
    try:
        edited = await sent.edit_caption(
            text, caption_entities=entities, reply_markup=reply_markup,
        )
        return edited or sent
    except Exception:
        try:
            edited = await sent.edit_caption(
                text,
                caption_entities=strip_custom_emoji_entities(entities),
                reply_markup=reply_markup,
            )
            return edited or sent
        except Exception:
            return sent


async def _member_status_in_chat(chat_id, user_id):
    """Trả (joined: bool|None, banned: bool, raw_status).

    Never-joined / LEFT / UserNotParticipant / member not found → (False, False, left).
    Chỉ BANNED/KICKED → banned=True. joined=None chỉ khi lỗi không phân loại được.
    """
    try:
        mem = await app.get_chat_member(chat_id, user_id)
    except Exception as e:
        err = str(e).lower()
        name = e.__class__.__name__.lower()
        # Mọi dạng "chưa/không phải thành viên" → missing (không phải banned)
        if (
            "usernotparticipant" in name
            or "user_not_participant" in err
            or "not a participant" in err
            or "not a member" in err
            or "member not found" in err
            or "participant_id_invalid" in err
            or "chat_member_invalid" in err
            or "peer_id_invalid" in err
            or "user_id_invalid" in err
        ):
            return False, False, "left"
        LOGGER.warning("get_chat_member chat=%s user=%s: %s", chat_id, user_id, e)
        return None, False, None
    status = mem.status
    is_member = getattr(mem, "is_member", None)
    kind = membership_check_result(status, is_member)
    if kind == "banned":
        return False, True, status
    if kind == "joined":
        return True, False, status
    return False, False, status


async def _ensure_promo_chat_id(kind: str, target: dict):
    """Lấy chat_id đã lưu hoặc resolve từ URL public rồi ghi Mongo."""
    cid = target.get("chat_id")
    if cid:
        return int(cid)
    url = target.get("url")
    username = public_username_from_tme_url(url or "")
    if not username:
        return None
    try:
        chat = await app.get_chat(username)
        cid = int(chat.id)
    except Exception as e:
        LOGGER.warning("resolve promo %s from %s failed: %s", kind, url, e)
        return None
    try:
        if kind == "channel":
            await set_up_link_channel(url, cid)
        else:
            await set_up_link_group(url, cid)
        target["chat_id"] = cid
        LOGGER.info("up promo %s chat_id backfilled: %s -> %s", kind, url, cid)
    except Exception as e:
        LOGGER.warning("save promo chat_id %s failed: %s", kind, e)
    return cid


async def _evaluate_join_gate(user_id: int):
    """Fail-closed: đã cấu hình link thì phải check được và user phải đang join."""
    targets = await get_up_promo_targets()
    configured = []
    results = {}
    for kind in ("channel", "group"):
        t = targets[kind]
        if not t.get("url") and not t.get("chat_id"):
            continue
        configured.append(kind)
        cid = await _ensure_promo_chat_id(kind, t)
        if not cid:
            results[kind] = "error"
            key = f"uncheckable:{kind}:{t.get('url')}"
            if key not in _nocheck_warned:
                _nocheck_warned.add(key)
                await _log_up(
                    f"{E_WARN} /up: không kiểm tra được <b>{kind}</b> "
                    f"(thiếu chat_id / không resolve được). <b>Không gửi file</b>."
                )
            continue
        joined, is_ban, raw = await _member_status_in_chat(cid, user_id)
        if joined is None:
            results[kind] = "error"
            key = f"fail:{kind}:{cid}"
            if key not in _nocheck_warned:
                _nocheck_warned.add(key)
                await _log_up(
                    f"{E_WARN} /up: lỗi get_chat_member <code>{cid}</code> ({kind}). "
                    f"<b>Không gửi file</b>. Kiểm tra bot còn admin."
                )
        elif is_ban:
            results[kind] = "banned"
        elif not joined:
            results[kind] = "missing"
        else:
            results[kind] = "joined"
        LOGGER.info(
            "up join-gate user=%s %s chat=%s -> %s raw=%s",
            user_id, kind, cid, results.get(kind), raw,
        )

    decision = evaluate_join_gate_decision(configured, results)
    decision["targets"] = targets
    decision["results"] = results
    # join prompt uses missing; if only errors, still show prompt
    if not decision["ok"] and not decision.get("banned") and not decision.get("missing"):
        decision["missing"] = list(decision.get("errors") or configured)
    return decision


async def _send_join_gate_prompt(message: Message, token: str, gate: dict):
    targets = gate["targets"]
    ch = targets["channel"]["url"]
    gr = targets["group"]["url"]
    text = (
        "Bạn cần tham gia Kênh và Nhóm chat trước khi tải file.\n\n"
        "Hãy bấm nút bên dưới để vào, rồi chọn Đã tham gia, tải file."
    )
    with skip_autodel():
        await message.reply_text(
            text,
            reply_markup=_join_gate_markup(token, ch, gr),
            no_autodel=True,
        )


async def _deliver_up_file_content(message: Message, rec: dict, token: str):
    with skip_autodel():
        return await _deliver_up_file_content_inner(message, rec, token)


async def _deliver_up_file_content_inner(message: Message, rec: dict, token: str):
    filename = rec.get("filename") or ""
    caption, followup = build_delivery_captions(
        name=rec.get("name") or "",
        version=rec.get("version") or "",
        bundle_id=rec.get("bundle_id") or "",
        store_url=rec.get("store_url") or "",
        features=normalize_stored_features(rec.get("features")),
    )
    markup = await _post_markup(token)
    try:
        await _send_document_html(
            message.chat.id,
            rec["file_id"],
            caption,
            file_name=filename or None,
            reply_markup=markup,
        )
    except Exception as e:
        try:
            if rec.get("file_chat_id") and rec.get("file_msg_id"):
                await app.copy_message(message.chat.id, rec["file_chat_id"], rec["file_msg_id"])
                if followup:
                    try:
                        await _send_html_text(message.chat.id, followup)
                    except Exception:
                        pass
                return True
        except Exception:
            pass
        await _reply_html(
            message,
            f"{E_ERROR} Không gửi được file: {html.escape(str(e))}",
        )
        return False
    if followup:
        try:
            await _send_html_text(message.chat.id, followup)
        except Exception:
            pass
    return True


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
    user = message.from_user
    if user and not _is_sudo_id(user.id):
        ban_rec = await get_leave_ban(user.id)
        gate = await _evaluate_join_gate(user.id)
        block = join_gate_block_kind(
            tg_banned=bool(gate.get("banned")),
            has_leave_ban_record=bool(ban_rec),
        )
        if block == "leave_ban":
            await message.reply_text(
                "Bạn đã bị cấm vì rời Kênh/Nhóm chat. Liên hệ admin để được mở lại."
            )
            return
        if block == "admin_ban":
            await message.reply_text(
                "Bạn đang bị cấm trong Kênh/Nhóm chat. Liên hệ admin để được mở lại."
            )
            return
        # LEFT / never-joined / error → join prompt (kể cả khi còn Mongo record cũ lệch)
        if ban_rec and not gate.get("banned"):
            # record auto-ban cũ nhưng Telegram không còn BANNED → xóa record lệch
            try:
                await clear_leave_ban(user.id)
                LOGGER.info("cleared stale leave-ban record user=%s", user.id)
            except Exception as e:
                LOGGER.warning("clear stale leave-ban user=%s: %s", user.id, e)
        if not gate["ok"]:
            await _send_join_gate_prompt(message, token, gate)
            return
    await _deliver_up_file_content(message, rec, token)


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



@app.on_callback_query(filters.regex(r"^upjoin_([0-9a-fA-F]+)$"), group=_HANDLER_GROUP)
@capture_err
async def upjoin_recheck(_, cq: CallbackQuery):
    if not cq.from_user:
        await cq.answer()
        return
    token = cq.matches[0].group(1).lower()
    rec = await get_up_file(token)
    if not rec or not rec.get("file_id"):
        await cq.answer("File không còn hiệu lực.", show_alert=True)
        return
    if _is_sudo_id(cq.from_user.id):
        await cq.answer("Đang gửi file...")
        # synthesize a message-like object for delivery chat
        class _M:
            pass
        m = cq.message
        await _deliver_up_file_content(m, rec, token)
        return
    ban_rec = await get_leave_ban(cq.from_user.id)
    gate = await _evaluate_join_gate(cq.from_user.id)
    block = join_gate_block_kind(
        tg_banned=bool(gate.get("banned")),
        has_leave_ban_record=bool(ban_rec),
    )
    if block == "leave_ban":
        await cq.answer("Bạn đã bị cấm vì rời Kênh/Nhóm. Liên hệ admin.", show_alert=True)
        try:
            await cq.message.edit_text(
                "Bạn đã bị cấm vì rời Kênh/Nhóm chat. Liên hệ admin để được mở lại."
            )
        except Exception:
            pass
        return
    if block == "admin_ban":
        await cq.answer("Bạn đang bị cấm trong Kênh/Nhóm. Liên hệ admin.", show_alert=True)
        try:
            await cq.message.edit_text(
                "Bạn đang bị cấm trong Kênh/Nhóm chat. Liên hệ admin để được mở lại."
            )
        except Exception:
            pass
        return
    if ban_rec and not gate.get("banned"):
        try:
            await clear_leave_ban(cq.from_user.id)
        except Exception:
            pass
    if not gate["ok"]:
        await cq.answer("Bạn chưa tham gia đủ Kênh và Nhóm chat.", show_alert=True)
        return
    await cq.answer("Đã xác nhận. Đang gửi file...")
    await _deliver_up_file_content(cq.message, rec, token)


@app.on_chat_member_updated(group=0)
async def up_leave_autoban(_, update: ChatMemberUpdated):
    """Tự ban khi user tự rời Kênh/Nhóm promo; xóa record khi admin unban."""
    try:
        targets = await get_up_promo_targets()
    except Exception:
        return
    watch = {
        targets["channel"]["chat_id"],
        targets["group"]["chat_id"],
    }
    watch.discard(None)
    if not watch or update.chat.id not in watch:
        return

    old = update.old_chat_member
    new = update.new_chat_member
    old_status = old.status if old else None
    new_status = new.status if new else None
    user = None
    if new and new.user:
        user = new.user
    elif old and old.user:
        user = old.user
    if not user or user.is_bot:
        return
    if _is_sudo_id(user.id):
        return

    # Admin unban detection: BANNED -> LEFT/MEMBER
    if old and new and should_clear_leave_ban_on_unban(old_status=old_status, new_status=new_status):
        # only clear if an admin performed it (from_user is admin)
        actor = update.from_user
        if actor and actor.id != user.id:
            await clear_leave_ban(user.id)
            await _log_up(
                f"{E_SUCCESS} /up: đã xóa record auto-ban của <code>{user.id}</code> "
                f"(admin unban trong {html.escape(update.chat.title or str(update.chat.id))})."
            )
        return

    # Voluntary leave ONLY: from_user must be the leaving user themself.
    # Thiếu from_user / admin kick / channel anonymous → không auto-ban.
    actor = update.from_user
    if not actor or actor.id != user.id:
        return
    effective_new = new_status
    if new is None and old is not None:
        effective_new = ChatMemberStatus.LEFT
    old_is_member = getattr(old, "is_member", None) if old else None
    if not should_autoban_on_leave(
        old_status=old_status,
        new_status=effective_new,
        user_is_bot=bool(user.is_bot),
        user_is_sudo=_is_sudo_id(user.id),
        left_by_admin=False,
        self_leave=True,
        old_is_member=old_is_member,
    ):
        return

    name = (user.first_name or "") + ((" " + user.last_name) if user.last_name else "")
    left_chat = update.chat.id
    banned_ok = []
    for cid in list(watch):
        try:
            await app.ban_chat_member(cid, user.id)
            banned_ok.append(str(cid))
        except Exception as e:
            LOGGER.warning("up autoban fail chat=%s user=%s: %s", cid, user.id, e)
    await save_leave_ban(user.id, {
        "name": name,
        "username": user.username or "",
        "left_chat_id": left_chat,
        "banned_chats": banned_ok,
        "banned_at": utc_timestamp(),
    })
    await _log_up(
        f"{E_WARN} /up auto-ban: <a href=\"tg://user?id={user.id}\">{html.escape(name or str(user.id))}</a> "
        f"(<code>{user.id}</code>) rời <code>{left_chat}</code> — "
        f"đã ban: {html.escape(', '.join(banned_ok) or 'không thành công')}."
    )


@app.on_message(filters.command(["up_unban"], COMMAND_HANDLER), group=_HANDLER_GROUP)
@capture_err
async def command_up_unban(_, message: Message):
    if not _is_sudo(message):
        await _reply_html(message, f"{E_WARN} Chỉ admin bot mới /up_unban được.")
        return
    target = None
    args = (message.text or "").split(maxsplit=1)
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user.id
    elif len(args) > 1:
        raw = args[1].strip()
        if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
            target = int(raw)
        else:
            try:
                user = await app.get_users(raw)
                target = user.id
            except Exception as e:
                await _reply_html(message, f"{E_ERROR} Không tìm user: {html.escape(str(e))}")
                return
    if not target:
        await _reply_html(
            message,
            f"{E_TIP} Dùng <code>/up_unban &lt;user_id|@user&gt;</code> hoặc trả lời tin của họ.",
        )
        return
    targets = await get_up_promo_targets()
    results = []
    for kind in ("channel", "group"):
        cid = targets[kind]["chat_id"]
        if not cid:
            results.append(f"{kind}: chưa cấu hình")
            continue
        try:
            await app.unban_chat_member(cid, target)
            results.append(f"{kind}: đã unban")
        except Exception as e:
            results.append(f"{kind}: lỗi {e}")
    await clear_leave_ban(target)
    await _reply_html(
        message,
        f"{E_SUCCESS} Đã xử lý unban <code>{target}</code>:\n"
        + "\n".join(html.escape(r) for r in results),
    )


@app.on_message(filters.command(["up_banlist"], COMMAND_HANDLER), group=_HANDLER_GROUP)
@capture_err
async def command_up_banlist(_, message: Message):
    if not _is_sudo(message):
        await _reply_html(message, f"{E_WARN} Chỉ admin bot mới xem /up_banlist.")
        return
    rows = await list_leave_bans(40)
    if not rows:
        await _reply_html(message, f"{E_TIP} Chưa có ai bị auto-ban vì rời Kênh/Nhóm.")
        return
    lines = [f"{E_TIP} <b>Danh sách auto-ban /up</b> ({len(rows)}):"]
    for rec in rows:
        uid = rec.get("user_id") or rec.get("_id")
        name = html.escape(str(rec.get("name") or ""))
        when = rec.get("banned_at")
        when_s = format_ts_vn(when, FMT_DM_HM) if when else "?"
        left = rec.get("left_chat_id") or "?"
        lines.append(f"• <code>{uid}</code> {name} — rời <code>{left}</code> lúc {when_s}")
    await _reply_html(message, "\n".join(lines))


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
        with skip_autodel():
            await app.send_message(
                target_id, user_text, parse_mode=enums.ParseMode.HTML, no_autodel=True,
            )
    except Exception:
        pass
