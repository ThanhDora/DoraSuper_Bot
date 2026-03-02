import contextlib
import typing

import pyrogram
from cachetools import TTLCache
from pyrogram.methods import Decorators

from dorasuper.emoji import E_ADMIN, E_CLOCK, E_GROUP, E_LOCK, E_TIP, E_WARN
from ..utils import check_rights, handle_error, is_admin

ANON = TTLCache(maxsize=250, ttl=30)
_ANON_HANDLER_ADDED = False

# Từ điển dịch quyền sang tiếng Việt
PERMISSION_TRANSLATIONS = {
    "can_post_messages": "Quyền đăng tin nhắn",
    "can_edit_messages": "Quyền chỉnh sửa tin nhắn",
    "can_delete_messages": "Quyền xóa tin nhắn",
    "can_restrict_members": "Quyền hạn chế thành viên",
    "can_promote_members": "Quyền thăng cấp thành viên",
    "can_change_info": "Quyền thay đổi thông tin",
    "can_invite_users": "Quyền mời người dùng",
    "can_pin_messages": "Quyền ghim tin nhắn",
    "can_manage_video_chats": "Quyền quản lý cuộc trò chuyện video"
}

async def anonymous_admin(m: pyrogram.types.Message):
    """
    Helper function for Anonymous Admin Verification
    """
    keyboard = pyrogram.types.InlineKeyboardMarkup(
        [
            [
                pyrogram.types.InlineKeyboardButton(
                    text="Xác minh!",
                    callback_data=f"anon.{m.id}",
                ),
            ]
        ]
    )
    return await m.reply_text(
        f"{E_TIP} Nhấp vào đây để chứng minh bạn là quản trị viên có đủ quyền thực hiện hành động này!",
        reply_markup=keyboard,
        parse_mode=pyrogram.enums.ParseMode.HTML,
    )

async def anonymous_admin_verification(
    self, CallbackQuery: pyrogram.types.CallbackQuery
):
    if int(
        f"{CallbackQuery.message.chat.id}{CallbackQuery.data.split('.')[1]}"
    ) not in set(ANON.keys()):
        try:
            await CallbackQuery.message.edit_text(f"{E_CLOCK} Nút đã hết hạn.", parse_mode=pyrogram.enums.ParseMode.HTML)
        except pyrogram.errors.RPCError:
            with contextlib.suppress(pyrogram.errors.RPCError):
                await CallbackQuery.message.delete()
        return
    cb = ANON.pop(
        int(f"{CallbackQuery.message.chat.id}{CallbackQuery.data.split('.')[1]}")
    )
    try:
        member = await CallbackQuery.message.chat.get_member(CallbackQuery.from_user.id)
    except pyrogram.errors.exceptions.bad_request_400.UserNotParticipant:
        return await CallbackQuery.answer(
            f"{E_WARN} Bạn không phải là thành viên của nhóm này.", show_alert=True
        )
    except pyrogram.errors.exceptions.forbidden_403.ChatAdminRequired:
        return await CallbackQuery.message.edit_text(
            f"{E_WARN} Tôi phải là quản trị viên để thực hiện nhiệm vụ này, nếu không tôi sẽ rời khỏi nhóm này.",
            parse_mode=pyrogram.enums.ParseMode.HTML,
        )
    if member.status not in (
        pyrogram.enums.ChatMemberStatus.OWNER,
        pyrogram.enums.ChatMemberStatus.ADMINISTRATOR,
    ):
        return await CallbackQuery.answer(f"{E_ADMIN} Bạn cần phải là quản trị viên để thực hiện việc này.")
    permission = cb[2]

    if isinstance(permission, str) and not await check_rights(
        CallbackQuery.message.chat.id,
        CallbackQuery.from_user.id,
        permission,
        client=self,
    ):
        # Dịch permission sang tiếng Việt
        translated_perm = PERMISSION_TRANSLATIONS.get(permission, permission)
        return await CallbackQuery.message.edit_text(
            f"Bạn đang thiếu quyền sau để sử dụng lệnh này:\n{translated_perm}",
            parse_mode=pyrogram.enums.ParseMode.HTML,
        )
    if isinstance(permission, list):
        permissions = ""
        for perm in permission:
            if not await check_rights(
                CallbackQuery.message.chat.id,
                CallbackQuery.from_user.id,
                perm,
                client=self,
            ):
                # Dịch từng permission sang tiếng Việt
                translated_perm = PERMISSION_TRANSLATIONS.get(perm, perm)
                permissions += f"\n{translated_perm}"
        if permissions != "":
            return await CallbackQuery.message.edit_text(
                f"Bạn không có quyền cần thiết để thực hiện lệnh này.\nQuyền cần thiết: {permissions}",
                parse_mode=pyrogram.enums.ParseMode.HTML,
            )
    try:
        await CallbackQuery.message.delete()
        await cb[1](self, cb[0])
    except pyrogram.errors.exceptions.forbidden_403.ChatAdminRequired:
        return await CallbackQuery.message.edit_text(
            f"{E_WARN} Tôi phải là quản trị viên để thực hiện nhiệm vụ này, nếu không tôi sẽ rời khỏi nhóm này.",
            parse_mode=pyrogram.enums.ParseMode.HTML,
        )
    except BaseException as e:
        return await handle_error(e, CallbackQuery)

def adminsOnly(
    self,
    permission: typing.Union[str, list],
    TRUST_ANON_ADMINS: typing.Union[bool, bool] = False,
):
    """
    # `tgEasy.tgClient.adminsOnly`
    - A decorater for running the function only if the admin have the specified Rights.
    - If the admin is Anonymous Admin, it also checks his rights by making a Callback.
    - Parameters:
    - permission (str):
        - Quyền mà người dùng phải có để sử dụng hàm

    - TRUST_ANON_ADMIN (bool) **optional**:
        - Nếu người dùng là Quản trị viên Ẩn danh, bỏ qua kiểm tra quyền.

    # Example
    .. code-block:: python
        from tgEasy import tgClient
        import pyrogram

        app = tgClient(pyrogram.Client())

        @app.command("start")
        @app.adminsOnly("can_change_info")
        async def start(client, message):
            await message.reply_text(f"Xin chào Quản trị viên {message.from_user.mention}")
    """

    def wrapper(func):
        async def decorator(client, message):
            permissions = ""
            _del = 6  # Tin lỗi tự xóa sau vài giây
            if message.chat.type != pyrogram.enums.ChatType.SUPERGROUP:
                return await message.reply_msg(
                    f"{E_GROUP} Lệnh này chỉ có thể sử dụng trong nhóm.", del_in=_del, parse_mode=pyrogram.enums.ParseMode.HTML
                )
            if message.sender_chat and not TRUST_ANON_ADMINS:
                ANON[int(f"{message.chat.id}{message.id}")] = (
                    message,
                    func,
                    permission,
                )
                return await anonymous_admin(message)
            if not await is_admin(
                message.chat.id,
                message.from_user.id,
                client=client,
            ):
                return await message.reply_msg(
                    f"{E_WARN} Bạn phải là quản trị viên để sử dụng lệnh này.", del_in=_del, parse_mode=pyrogram.enums.ParseMode.HTML
                )
            if isinstance(permission, str) and not await check_rights(
                message.chat.id,
                message.from_user.id,
                permission,
                client=client,
            ):
                # Dịch permission sang tiếng Việt
                translated_perm = PERMISSION_TRANSLATIONS.get(permission, permission)
                return await message.reply_msg(
                    f"Bạn không có quyền cần thiết để thực hiện lệnh này.\nQuyền cần thiết: <code>{translated_perm}</code>", del_in=_del, parse_mode=pyrogram.enums.ParseMode.HTML
                )
            if isinstance(permission, list):
                for perm in permission:
                    if not await check_rights(
                        message.chat.id,
                        message.from_user.id,
                        perm,
                        client=client,
                    ):
                        # Dịch từng permission sang tiếng Việt
                        translated_perm = PERMISSION_TRANSLATIONS.get(perm, perm)
                        permissions += f"\n{translated_perm}"
                if permissions != "":
                    return await message.reply_msg(
                        f"Bạn không có quyền cần thiết để thực hiện lệnh này.\nQuyền cần thiết: {permissions}", del_in=_del, parse_mode=pyrogram.enums.ParseMode.HTML
                    )
            try:
                await func(client, message)
            except pyrogram.errors.exceptions.forbidden_403.ChatWriteForbidden:
                await client.leave_chat(message.chat.id)
            except BaseException as exception:
                await handle_error(exception, message)

        global _ANON_HANDLER_ADDED
        if not _ANON_HANDLER_ADDED:
            _ANON_HANDLER_ADDED = True
            self.add_handler(
                pyrogram.handlers.CallbackQueryHandler(
                    anonymous_admin_verification,
                    pyrogram.filters.regex("^anon."),
                ),
            )
        return decorator

    return wrapper

Decorators.adminsOnly = adminsOnly