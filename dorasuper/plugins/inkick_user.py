import time
import logging
from logging import getLogger
from asyncio import sleep

from pyrogram import enums, filters
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChatAdminRequired,
    UserAdminInvalid,
)
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden

from dorasuper import app
from dorasuper.emoji import E_ANDROID, E_CLOCK, E_DORA1, E_DORA2, E_DORA3, E_DORA4, E_GROUP, E_LIMIT, E_MENU, E_BAN, E_LOADING, E_ERROR, E_SUCCESS
from dorasuper.vars import COMMAND_HANDLER

LOGGER = getLogger("DoraSuper")

__MODULE__ = "SiêuQuảnTrị"
__HELP__ = """
<code>/trangthai</code> - Xem trạng thái thành viên trong nhóm.
<code>/cam_ghosts</code> - Xóa tài khoản đã xóa khỏi nhóm.
<code>/sutkhonguname</code> - Xóa tài khoản không có tên người dùng khỏi nhóm.
"""


@app.on_message(
    filters.incoming & ~filters.private & filters.command(["inkick"], COMMAND_HANDLER)
)
@app.adminsOnly("can_restrict_members")
async def inkick(_, message):
    user = await app.get_chat_member(message.chat.id, message.from_user.id)
    if user.status.value in ("administrator", "owner"):
        if len(message.command) > 1:
            input_str = message.command
            sent_message = await message.reply_text(
                f"{E_LOADING} **Hiện đang dọn dẹp người dùng, có thể mất một lúc...**"
            )
            count = 0
            async for member in app.get_chat_members(message.chat.id):
                if member.user.is_bot:
                    continue
                if (
                    member.user.status.value in input_str
                    and member.status.value not in ("administrator", "owner")
                ):
                    try:
                        await message.chat.ban_member(member.user.id)
                        count += 1
                        await sleep(1)
                        await message.chat.unban_member(member.user.id)
                    except (ChatAdminRequired, UserAdminInvalid):
                        await sent_message.edit(
                            f"{E_ERROR} **Ôi không, tôi không phải là quản trị viên ở đây**\n__Tôi sẽ rời khỏi đây, thêm lại tôi với quyền đầy đủ_"
                        )
                        await app.leave_chat(message.chat.id)
                        break
                    except FloodWait as e:
                        await sleep(e.value)
                        await message.chat.ban_member(member.user.id)
                        await message.chat.unban_member(member.user.id)
            try:
                await sent_message.edit(
                    f"{E_SUCCESS} **Đã loại bỏ thành công {count} người dùng dựa trên các đối số.**"
                )

            except ChatWriteForbidden:
                await app.leave_chat(message.chat.id)
        else:
            await message.reply_text(
                f"{E_ERROR} **Các lập luận bắt buộc**\n__Xem /help trong tin nhắn cá nhân để biết thêm thông tin.__"
            )
    else:
        sent_message = await message.reply_text(
            f"{E_ERROR} **Bạn phải là người tạo nhóm để làm điều đó.**"
        )
        await sleep(5)
        await sent_message.delete()


# Kick User Without Username
@app.on_message(
    filters.incoming & ~filters.private & filters.command(["sutkhonguname"], COMMAND_HANDLER)
)
@app.adminsOnly("can_restrict_members")
async def uname(_, message):
    user = await app.get_chat_member(message.chat.id, message.from_user.id)
    if user.status.value in ("administrator", "owner"):
        sent_message = await message.reply_text(
            f"{E_LOADING} **Hiện đang dọn dẹp người dùng, có thể mất một lúc...**"
        )
        count = 0
        async for member in app.get_chat_members(message.chat.id):
            if not member.user.username and member.status.value not in (
                "administrator",
                "owner",
            ):
                try:
                    await message.chat.ban_member(member.user.id)
                    count += 1
                    await sleep(1)
                    await message.chat.unban_member(member.user.id)
                except (ChatAdminRequired, UserAdminInvalid):
                    await sent_message.edit(
                        "❗**Ôi không, tôi không phải là quản trị viên ở đây**\n__Tôi sẽ rời khỏi đây, thêm lại tôi với quyền đầy đủ_"
                    )
                    await app.leave_chat(message.chat.id)
                    break
                except FloodWait as e:
                    await sleep(e.value)
                    await message.chat.ban_member(member.user.id)
                    await message.chat.unban_member(member.user.id)
        try:
            await sent_message.edit(
                f"✔️ **Đã loại bỏ thành công {count} người dùng dựa trên các đối số.**"
            )

        except ChatWriteForbidden:
            await app.leave_chat(message.chat.id)
    else:
        sent_message = await message.reply_text(
            "❗ **Bạn phải là người tạo nhóm để làm điều đó.**"
        )
        await sleep(5)
        await sent_message.delete()


@app.on_message(
    filters.incoming
    & ~filters.private
    & filters.command(["cam_ghosts"], COMMAND_HANDLER)
)
@app.adminsOnly("can_restrict_members")
async def rm_delacc(_, message):
    user = await app.get_chat_member(message.chat.id, message.from_user.id)
    if user.status.value in ("administrator", "owner"):
        sent_message = await message.reply_text(
            f"{E_LOADING} **Hiện đang dọn dẹp người dùng, có thể mất một lúc...**"
        )
        count = 0
        async for member in app.get_chat_members(message.chat.id):
            if member.user.is_deleted and member.status.value not in (
                "administrator",
                "owner",
            ):
                try:
                    await message.chat.ban_member(member.user.id)
                    count += 1
                    await sleep(1)
                    await message.chat.unban_member(member.user.id)
                except (ChatAdminRequired, UserAdminInvalid):
                    await sent_message.edit(
                        f"{E_ERROR} **Ôi không, tôi không phải là quản trị viên ở đây**\n__Tôi sẽ rời khỏi đây, thêm lại tôi với quyền đầy đủ_"
                    )
                    break
                except FloodWait as e:
                    await sleep(e.value)
                    await message.chat.ban_member(member.user.id)
                    await message.chat.unban_member(member.user.id)
        if count == 0:
            return await sent_message.edit_msg(
                f"{E_ERROR} **Không có tài khoản nào bị xóa trong cuộc trò chuyện này.**"
            )
        await sent_message.edit_msg(f"{E_SUCCESS} **Đã loại bỏ thành công {count} người dùng dựa trên các đối số.**")
    else:
        sent_message = await message.reply_text(
            f"{E_ERROR} **Bạn phải là quản trị viên hoặc chủ sở hữu nhóm để thực hiện hành động này.**"
        )
        await sleep(5)
        await sent_message.delete()

@app.on_message(
    filters.incoming & ~filters.private & filters.command(["trangthai"], COMMAND_HANDLER)
)
@app.adminsOnly("can_restrict_members")
async def instatus(client, message):
    bstat = await app.get_chat_member(message.chat.id, client.me.id)
    if bstat.status.value != "administrator":
        return await message.reply_msg(
            f"{E_ERROR} **Vui lòng cấp cho tôi tất cả quyền quản trị viên cơ bản để chạy lệnh này.**"
        )
    start_time = time.perf_counter()
    user = await app.get_chat_member(message.chat.id, message.from_user.id)
    count = await app.get_chat_members_count(message.chat.id)
    if user.status in (
        enums.ChatMemberStatus.ADMINISTRATOR,
        enums.ChatMemberStatus.OWNER,
    ):
        sent_message = await message.reply_text(
            f"{E_LOADING} **Hiện đang thu thập thông tin người dùng...**"
        )
        recently = 0
        within_week = 0
        within_month = 0
        long_time_ago = 0
        deleted_acc = 0
        premium_acc = 0
        no_username = 0
        restricted = 0
        banned = 0
        uncached = 0
        bot = 0
        async for _ in app.get_chat_members(
            message.chat.id, filter=enums.ChatMembersFilter.BANNED
        ):
            banned += 1
        async for _ in app.get_chat_members(
            message.chat.id, filter=enums.ChatMembersFilter.RESTRICTED
        ):
            restricted += 1
        async for member in app.get_chat_members(message.chat.id):
            user = member.user
            if user.is_deleted:
                deleted_acc += 1
            elif user.is_bot:
                bot += 1
            elif user.is_premium:
                premium_acc += 1
            elif not user.username:
                no_username += 1
            elif user.status.value == "recently":
                recently += 1
            elif user.status.value == "last_week":
                within_week += 1
            elif user.status.value == "last_month":
                within_month += 1
            elif user.status.value == "long_ago":
                long_time_ago += 1
            else:
                uncached += 1
        end_time = time.perf_counter()
        timelog = "{:.2f}".format(end_time - start_time)
        await sent_message.edit_msg(
            (
                f"<b>{E_MENU} {message.chat.title}\n{E_GROUP} {count} Thành viên\n——————\n"
                f"Thông tin trạng thái thành viên\n——————\n</b>"
                f"{E_CLOCK} Tham gia gần đây: {recently}\n"
                f"{E_CLOCK} Tham gia trong tuần: {within_week}\n"
                f"{E_CLOCK} Tham gia trong tháng: {within_month}\n"
                f"{E_CLOCK} Tham gia từ lâu: {long_time_ago}\n"
                f"{E_DORA2} Không có tên người dùng: {no_username}\n"
                f"{E_LIMIT} Bị cấm chat trong nhóm: {restricted}\n"
                f"{E_BAN} Bị cấm tham gia nhóm: {banned}\n"
                f"{E_DORA4} Tài khoản không tồn tại (<code>/cam_ghosts</code>): {deleted_acc}\n"
                f"{E_ANDROID} Bot: {bot}\n"
                f"{E_DORA3} Người dùng Premium: {premium_acc}\n"
                f"{E_DORA1} Chưa được cache: {uncached}\n\n"
                f"{E_CLOCK} Thực hiện trong {timelog} ms"
            ),
            parse_mode=enums.ParseMode.HTML,
        )
    else:
        sent_message = await message.reply_text(
            f"{E_ERROR} **Bạn phải là quản trị viên hoặc chủ sở hữu nhóm để thực hiện hành động này.**"
        )
        await sleep(5)
        await sent_message.delete()
