"""Danh sách trắng: không thể bị mute/cấm/đá; tự động bỏ cấm nếu bị hạn chế thủ công."""
from __future__ import annotations

import html
import time
from logging import getLogger

from pyrogram import enums, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import ChatAdminRequired, PeerIdInvalid, UsernameNotOccupied, UserNotParticipant
from pyrogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.chat_ban_db import remove_chat_ban
from database.chat_mute_db import remove_chat_mute
from database.gban_db import remove_gban_user
from database.whitelist_db import (
    add_global_whitelist,
    add_whitelist,
    is_whitelisted,
    list_global_whitelist,
    list_whitelist,
    remove_global_whitelist,
    remove_whitelist,
)
from dorasuper import app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.core.decorator.permissions import member_permissions
from dorasuper.emoji import E_SUCCESS, E_WARN
from dorasuper.helper.functions import extract_user
from dorasuper.helper.whitelist import (
    GLOBAL_CHAT_ID,
    auto_restore_html,
    missing_rights_html,
    protected_html,
    reply_and_autodel,
    schedule_whitelist_autodel,
    should_auto_restore,
    should_dedupe_restore,
    split_scope,
)
from dorasuper.vars import COMMAND_HANDLER, SUDO

LOGGER = getLogger("DoraSuper")

__MODULE__ = "DanhSáchTrắng"
__HELP__ = """
Người trong danh sách trắng không thể bị mute, cấm hoặc đá bởi bot. Nếu bị cấm hoặc hạn chế thủ công (hoặc bởi bot khác), bot sẽ tự động bỏ cấm/gỡ hạn chế.

<blockquote>/whitelist – Xem danh sách trắng của nhóm
/whitelist [trả lời | @user | id] – Thêm vào danh sách trắng của nhóm
/unwhitelist [trả lời | @user | id] – Gỡ khỏi danh sách trắng của nhóm
/whitelists – Xem danh sách trắng của nhóm

Chủ bot:
/whitelist global [trả lời | @user | id] – Thêm danh sách trắng toàn cục
/unwhitelist global [trả lời | @user | id] – Gỡ danh sách trắng toàn cục
/gwhitelist [trả lời | @user | id] – Thêm danh sách trắng toàn cục
/ungwhitelist [trả lời | @user | id] – Gỡ danh sách trắng toàn cục
/gwhitelists – Xem danh sách trắng toàn cục</blockquote>
"""

_PAGE_SIZE = 15
_HANDLER_GROUP_AUTO = 6
# Pyrofork runs only the first matching handler in a group, then moves on.
# AFK (and other) catch-alls in group=0 would swallow /whitelist; use -1 like /help, /ping.
_HANDLER_GROUP_CMD = -1
_recent_restores: dict[tuple[int, int], float] = {}


def _claim_restore(chat_id: int, user_id: int) -> bool:
    """Claim this chat+user incident. False if a notice was just sent."""
    now = time.time()
    key = (int(chat_id), int(user_id))
    if should_dedupe_restore(_recent_restores.get(key), now):
        return False
    _recent_restores[key] = now
    if len(_recent_restores) > 500:
        cutoff = now - 60
        for stale in [k for k, ts in _recent_restores.items() if ts < cutoff]:
            _recent_restores.pop(stale, None)
    return True


async def _reply(message: Message, text: str, **kwargs):
    kwargs.setdefault("parse_mode", enums.ParseMode.HTML)
    kwargs.setdefault("quote", True)
    return await reply_and_autodel(
        message.reply_text, text, client=app, user_message=message, **kwargs
    )


def _is_sudo(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in (SUDO or []))


def _mention_from_user(user) -> str:
    if not user:
        return "Người dùng này"
    try:
        return user.mention
    except Exception:
        uid = getattr(user, "id", None)
        name = html.escape(getattr(user, "first_name", None) or str(uid or ""))
        if uid:
            return f"<a href='tg://user?id={uid}'>{name}</a>"
        return name or "Người dùng này"


def _display_name(doc: dict) -> str:
    name = html.escape((doc or {}).get("name") or "")
    uid = (doc or {}).get("user_id")
    if name:
        return f"{name} — <code>{uid}</code>"
    return f"<code>{uid}</code>"


async def _can_manage(message: Message) -> bool:
    if _is_sudo(message):
        return True
    if not message.from_user or not message.chat:
        return False
    if message.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return False
    perms = await member_permissions(message.chat.id, message.from_user.id)
    return "can_restrict_members" in (perms or [])


async def _resolve_target(message: Message, leftover: list[str]):
    """Resolve target from reply, leftover args, or extract_user. Returns (user_id, mention, err)."""
    if leftover:
        token = leftover[0]
        try:
            user = await app.get_users(int(token) if token.lstrip("-").isdigit() else token)
            mention = _mention_from_user(user)
            return user.id, mention, (user.first_name or "") + ((" " + user.last_name) if user.last_name else "")
        except (PeerIdInvalid, UsernameNotOccupied, ValueError, KeyError, IndexError, Exception):
            return None, None, None
    try:
        user_id = await extract_user(message)
    except (PeerIdInvalid, UsernameNotOccupied):
        return None, None, None
    if not user_id:
        return None, None, None
    try:
        user = await app.get_users(user_id)
        mention = _mention_from_user(user)
        name = (user.first_name or "") + ((" " + user.last_name) if user.last_name else "")
        return user.id, mention, name
    except Exception:
        return int(user_id), f"<code>{user_id}</code>", ""


def _list_markup(kind: str, chat_id: int, page: int, pages: int):
    if pages <= 1:
        return None
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("Trang trước", callback_data=f"wl_list:{kind}:{chat_id}:{page - 1}"))
    if page < pages - 1:
        row.append(InlineKeyboardButton("Trang sau", callback_data=f"wl_list:{kind}:{chat_id}:{page + 1}"))
    return InlineKeyboardMarkup([row]) if row else None


def _render_list(kind: str, chat_id: int, rows: list, page: int = 0):
    if kind == "g":
        title = "Danh sách trắng toàn cục:"
    else:
        title = "Danh sách trắng của nhóm này:"
    total = len(rows)
    if total == 0:
        return f"{title}\n\nChưa có ai trong danh sách.", None
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * _PAGE_SIZE
    chunk = rows[start:start + _PAGE_SIZE]
    lines = [title, f"Tổng: {total} — Trang {page + 1}/{pages}", ""]
    for i, doc in enumerate(chunk, start=start + 1):
        lines.append(f"{i}. {_display_name(doc)}")
    if kind == "g":
        lines.append("\nDùng /ungwhitelist để gỡ.")
    else:
        lines.append("\nDùng /unwhitelist để gỡ.")
    return "\n".join(lines), _list_markup(kind, chat_id, page, pages)


async def _lift_in_chat(client, chat_id: int, user_id: int) -> None:
    """Unban/unrestrict if currently limited, and clear local ban/mute records."""
    try:
        await remove_chat_ban(chat_id, user_id)
        await remove_chat_mute(chat_id, user_id)
    except Exception:
        pass
    try:
        member = await client.get_chat_member(chat_id, user_id)
        status = member.status
        if status == ChatMemberStatus.BANNED:
            await client.unban_chat_member(chat_id, user_id)
        elif status == ChatMemberStatus.RESTRICTED:
            chat = await client.get_chat(chat_id)
            perms = getattr(chat, "permissions", None)
            if perms:
                await client.restrict_chat_member(chat_id, user_id, permissions=perms)
            else:
                await client.unban_chat_member(chat_id, user_id)
    except UserNotParticipant:
        try:
            await client.unban_chat_member(chat_id, user_id)
        except Exception:
            pass
    except (ChatAdminRequired, PeerIdInvalid):
        pass
    except Exception as e:
        LOGGER.debug("whitelist lift_in_chat chat=%s user=%s: %s", chat_id, user_id, e)


async def _usage(message: Message, global_scope: bool):
    if global_scope:
        text = (
            f"{E_WARN} Cách dùng (chỉ chủ bot):\n"
            "<code>/whitelist global [trả lời | @user | id]</code>\n"
            "<code>/gwhitelist [trả lời | @user | id]</code>\n"
            "<code>/gwhitelists</code> — xem danh sách toàn cục."
        )
    else:
        text = (
            f"{E_WARN} Cách dùng:\n"
            "<code>/whitelist</code> hoặc <code>/whitelists</code> — xem danh sách của nhóm\n"
            "<code>/whitelist [trả lời | @user | id]</code> — thêm\n"
            "<code>/unwhitelist [trả lời | @user | id]</code> — gỡ."
        )
    await _reply(message, text, parse_mode=enums.ParseMode.HTML, quote=True)


@app.on_message(filters.command(["whitelist", "whitelists", "gwhitelist", "gwhitelists"], COMMAND_HANDLER), group=_HANDLER_GROUP_CMD)
@capture_err
async def whitelist_cmd(_, message: Message):
    cmd = (message.command or ["whitelist"])[0].lower()
    LOGGER.info(
        "whitelist cmd=%s chat_id=%s user_id=%s",
        cmd,
        getattr(message.chat, "id", None),
        getattr(message.from_user, "id", None),
    )
    raw_args = list(message.command[1:]) if message.command and len(message.command) > 1 else []
    is_list_alias = cmd in {"whitelists", "gwhitelists"}
    force_global = cmd in {"gwhitelist", "gwhitelists"}
    scoped, leftover = split_scope(raw_args)
    global_scope = force_global or scoped

    if global_scope and not _is_sudo(message):
        return await _reply(message, 
            f"{E_WARN} Chỉ chủ bot mới quản lý danh sách trắng toàn cục.",
            parse_mode=enums.ParseMode.HTML,
            quote=True,
        )

    # /whitelist (no args, no reply) or /whitelists = list; reply or @user/id = add
    want_list = is_list_alias or (not leftover and not message.reply_to_message)
    if want_list:
        if global_scope:
            rows = await list_global_whitelist()
            text, markup = _render_list("g", GLOBAL_CHAT_ID, rows, 0)
            return await _reply(message, 
                text, reply_markup=markup, parse_mode=enums.ParseMode.HTML, quote=True
            )
        if message.chat.type == ChatType.PRIVATE:
            return await _reply(message, 
                f"{E_WARN} <b>Danh sách trắng theo nhóm</b> phải dùng trong nhóm "
                "(ví dụ: <code>/whitelist</code> để xem, <code>/whitelist</code> trả lời tin người cần thêm).\n"
                "Chủ bot có thể dùng trong chat riêng: <code>/gwhitelists</code> để xem, "
                "<code>/gwhitelist [id|@user]</code> để thêm toàn cục.",
                parse_mode=enums.ParseMode.HTML,
                quote=True,
            )
        if not await _can_manage(message):
            return await _reply(message, 
                f"{E_WARN} Bạn cần quyền hạn chế thành viên để xem hoặc sửa danh sách trắng.",
                parse_mode=enums.ParseMode.HTML,
                quote=True,
            )
        rows = await list_whitelist(message.chat.id)
        text, markup = _render_list("c", message.chat.id, rows, 0)
        return await _reply(message, 
            text, reply_markup=markup, parse_mode=enums.ParseMode.HTML, quote=True
        )

    # add
    if message.chat.type == ChatType.PRIVATE and not global_scope:
        return await _reply(message, 
            f"{E_WARN} Thêm danh sách trắng theo nhóm phải dùng trong nhóm.",
            parse_mode=enums.ParseMode.HTML,
            quote=True,
        )
    if not global_scope and not await _can_manage(message):
        return await _reply(message, 
            f"{E_WARN} Bạn cần quyền hạn chế thành viên để thêm vào danh sách trắng.",
            parse_mode=enums.ParseMode.HTML,
            quote=True,
        )

    user_id, mention, name = await _resolve_target(message, leftover)
    if not user_id:
        return await _usage(message, global_scope)
    if message.from_user and user_id == message.from_user.id and not leftover and not message.reply_to_message:
        # extract_user may fall through oddly; still allow self-add if they passed an id
        pass
    bot_id = getattr(app.me, "id", None)
    if bot_id and user_id == bot_id:
        return await _reply(message, 
            f"{E_WARN} Không thể thêm bot vào danh sách trắng.",
            parse_mode=enums.ParseMode.HTML,
            quote=True,
        )

    added_by = message.from_user.id if message.from_user else 0
    if global_scope:
        added = await add_global_whitelist(user_id, added_by=added_by, name=name or "")
        try:
            await remove_gban_user(user_id)
        except Exception:
            pass
        if message.chat.type in (ChatType.SUPERGROUP, ChatType.GROUP):
            await _lift_in_chat(app, message.chat.id, user_id)
        scope_txt = "danh sách trắng toàn cục"
    else:
        added = await add_whitelist(message.chat.id, user_id, added_by=added_by, name=name or "")
        await _lift_in_chat(app, message.chat.id, user_id)
        scope_txt = "danh sách trắng của nhóm này"

    if added:
        text = f"{E_SUCCESS} Đã thêm {mention} vào {scope_txt}."
    else:
        text = f"{E_WARN} {mention} đã có trong {scope_txt}."
    await _reply(message, text, parse_mode=enums.ParseMode.HTML, quote=True)


@app.on_message(filters.command(["unwhitelist", "ungwhitelist"], COMMAND_HANDLER), group=_HANDLER_GROUP_CMD)
@capture_err
async def unwhitelist_cmd(_, message: Message):
    cmd = (message.command or ["unwhitelist"])[0].lower()
    LOGGER.info(
        "unwhitelist cmd=%s chat_id=%s user_id=%s",
        cmd,
        getattr(message.chat, "id", None),
        getattr(message.from_user, "id", None),
    )
    raw_args = list(message.command[1:]) if message.command and len(message.command) > 1 else []
    scoped, leftover = split_scope(raw_args)
    global_scope = cmd == "ungwhitelist" or scoped

    if global_scope and not _is_sudo(message):
        return await _reply(message, 
            f"{E_WARN} Chỉ chủ bot mới gỡ danh sách trắng toàn cục.",
            parse_mode=enums.ParseMode.HTML,
            quote=True,
        )
    if not global_scope:
        if message.chat.type == ChatType.PRIVATE:
            return await _reply(message, 
                f"{E_WARN} Gỡ danh sách trắng theo nhóm phải dùng trong nhóm.",
                parse_mode=enums.ParseMode.HTML,
                quote=True,
            )
        if not await _can_manage(message):
            return await _reply(message, 
                f"{E_WARN} Bạn cần quyền hạn chế thành viên để gỡ danh sách trắng.",
                parse_mode=enums.ParseMode.HTML,
                quote=True,
            )

    user_id, mention, _name = await _resolve_target(message, leftover)
    if not user_id:
        return await _usage(message, global_scope)

    if global_scope:
        removed = await remove_global_whitelist(user_id)
        scope_txt = "danh sách trắng toàn cục"
    else:
        removed = await remove_whitelist(message.chat.id, user_id)
        scope_txt = "danh sách trắng của nhóm này"

    if removed:
        text = f"{E_SUCCESS} Đã gỡ {mention} khỏi {scope_txt}."
    else:
        text = f"{E_WARN} {mention} không có trong {scope_txt}."
    await _reply(message, text, parse_mode=enums.ParseMode.HTML, quote=True)


@app.on_callback_query(filters.regex(r"^wl_list:(c|g):(-?\d+):(\d+)$"))
async def whitelist_list_page(_, cq: CallbackQuery):
    if not cq.from_user:
        return await cq.answer()
    kind, chat_id_s, page_s = cq.data.split(":")[1:]
    chat_id = int(chat_id_s)
    page = int(page_s)
    if kind == "g":
        if cq.from_user.id not in (SUDO or []):
            return await cq.answer("Chỉ chủ bot mới xem danh sách toàn cục.", show_alert=True)
        rows = await list_global_whitelist()
        text, markup = _render_list("g", GLOBAL_CHAT_ID, rows, page)
    else:
        if cq.message and cq.message.chat and cq.message.chat.id != chat_id:
            return await cq.answer("Danh sách này thuộc nhóm khác.", show_alert=True)
        perms = await member_permissions(chat_id, cq.from_user.id)
        if cq.from_user.id not in (SUDO or []) and "can_restrict_members" not in (perms or []):
            return await cq.answer("Bạn không có quyền xem danh sách này.", show_alert=True)
        rows = await list_whitelist(chat_id)
        text, markup = _render_list("c", chat_id, rows, page)
    try:
        edited = await cq.message.edit_text(text, reply_markup=markup, parse_mode=enums.ParseMode.HTML)
        await schedule_whitelist_autodel(app, edited or cq.message)
    except Exception:
        pass
    await cq.answer()


async def _restore_protected_member(chat, user, action: str) -> None:
    mention = _mention_from_user(user)
    chat_id = chat.id
    user_id = user.id
    try:
        if action == "unban":
            await app.unban_chat_member(chat_id, user_id)
            await remove_chat_ban(chat_id, user_id)
        else:
            # unban_chat_member fully lifts a mute (same as /boimmom), leaving MEMBER
            # rather than a still-RESTRICTED member with default permissions.
            try:
                await app.unban_chat_member(chat_id, user_id)
            except Exception:
                try:
                    chat_full = await app.get_chat(chat_id)
                    perms = getattr(chat_full, "permissions", None)
                except Exception:
                    perms = None
                if perms:
                    await app.restrict_chat_member(chat_id, user_id, permissions=perms)
            await remove_chat_mute(chat_id, user_id)
        try:
            notice = await app.send_message(
                chat_id,
                auto_restore_html(action, mention),
                parse_mode=enums.ParseMode.HTML,
                no_autodel=True,
            )
            await schedule_whitelist_autodel(app, notice)
        except Exception:
            pass
    except ChatAdminRequired:
        LOGGER.warning(
            "whitelist auto-restore missing rights chat=%s user=%s action=%s",
            chat_id, user_id, action,
        )
        try:
            notice = await app.send_message(
                chat_id,
                missing_rights_html(mention),
                parse_mode=enums.ParseMode.HTML,
                no_autodel=True,
            )
            await schedule_whitelist_autodel(app, notice)
        except Exception:
            pass
    except Exception as e:
        LOGGER.warning(
            "whitelist auto-restore failed chat=%s user=%s action=%s: %s",
            chat_id, user_id, action, e,
        )


@app.on_chat_member_updated(group=_HANDLER_GROUP_AUTO)
async def whitelist_auto_unban(_, update: ChatMemberUpdated):
    new = update.new_chat_member
    if not new or not new.user:
        return
    user = new.user
    if user.is_bot:
        return
    chat = update.chat
    if not chat:
        return
    try:
        protected = await is_whitelisted(chat.id, user.id)
    except Exception as e:
        LOGGER.debug("whitelist check failed: %s", e)
        return
    bot_id = getattr(getattr(app, "me", None), "id", None)
    actor = update.from_user
    actor_is_self_bot = bool(bot_id and actor and actor.id == bot_id)
    old_member = update.old_chat_member
    action = should_auto_restore(
        is_protected=protected,
        user_is_bot=bool(user.is_bot),
        new_status=new.status,
        old_status=old_member.status if old_member else None,
        actor_is_self_bot=actor_is_self_bot,
    )
    if not action:
        return
    if not _claim_restore(chat.id, user.id):
        LOGGER.debug("whitelist auto-restore deduped chat=%s user=%s", chat.id, user.id)
        return
    await _restore_protected_member(chat, user, action)
