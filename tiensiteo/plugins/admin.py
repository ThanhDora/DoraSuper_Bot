import asyncio
import os
import re
import logging
from logging import getLogger
from time import time

from pyrogram import Client, enums, filters
from pyrogram.errors import (
    ChatAdminRequired,
    FloodWait,
    PeerIdInvalid,
    UsernameNotOccupied,
    UserNotParticipant,
)
from pyrogram.types import ChatMember, ChatPermissions, ChatPrivileges, Message

from database.warn_db import add_warn, get_warn, remove_warns
from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.core.decorator.permissions import (
    admins_in_chat,
    list_admins,
    member_permissions,
)
from tiensiteo.core.keyboard import ikb
from tiensiteo.helper.functions import (
    extract_user,
    extract_user_and_reason,
    int_to_alpha,
    time_converter,
)
from tiensiteo.helper.localization import use_chat_lang
from tiensiteo.vars import COMMAND_HANDLER, SUDO

LOGGER = getLogger("TienSiTeo")

__MODULE__ = "AdminNhóm"
__HELP__ = """
<blockquote>/dsadmin - Danh sách các Admin trong nhóm  
/cam - Cấm một người dùng khỏi nhóm  
/xcam - Xóa tin nhắn được trả lời và cấm người gửi  
/tcam - Cấm một người dùng trong một thời gian cụ thể  
/bocam - Bỏ cấm một người dùng  
/camds - Cấm một người dùng khỏi các nhóm được liệt kê trong tin nhắn  
/bocamds - Bỏ cấm một người dùng khỏi các nhóm được liệt kê trong tin nhắn  
/canhbao - Cảnh cáo một người dùng  
/xcanhbao - Xóa tin nhắn được trả lời và cảnh cáo người gửi  
/gocanhbao - Xóa tất cả cảnh cáo của một người dùng  
/xemcanhbao - Hiển thị cảnh cáo của một người dùng  
/sut - Đuổi một người dùng  
/xsut - Xóa tin nhắn được trả lời và đuổi người gửi  
/xoanhieu [n + trả lời tin nhắn] - Xóa "n" số lượng tin nhắn từ tin nhắn được trả lời hoặc xóa tất cả tin nhắn từ tin nhắn được trả lời đến mới nhất.
/xoa - Xóa tin nhắn được trả lời  
/thangcap - Thăng chức một thành viên  
/fullthangcap - Thăng chức một thành viên với tất cả quyền hạn  
/hacap - Giáng chức một thành viên  
/ghim - Ghim một tin nhắn
/boghim - Bỏ ghim một tin nhắn
/immom - Tắt tiếng một người dùng  
/timom - Tắt tiếng một người dùng trong một thời gian cụ thể  
/boimmom - Bỏ tắt tiếng một người dùng  
/cam_ghosts - Cấm các tài khoản đã bị xóa  
/baocao | @admins - Báo cáo một tin nhắn cho quản trị viên  
/doiten - Thay đổi tên của một nhóm/kênh  
/doianh - Thay đổi ảnh đại diện của một nhóm/kênh  
/tagall - Nhắc đến tất cả thành viên trong một nhóm
/camthoat - Cấm người dùng khi họ tự ý rời khởi nhóm
/chaomung - Bật tắt chức năng chào mừng thành viên mới
/tinchaomung nội dung (tên_nút_1)[url_1] (tên_nút_2)[url_2] - Tạo tin nhắn chào mừng tùy chỉnh với nội dung và các nút inline. Định dạng: *đậm*, _nghiêng_, __gạch dưới__, `mã`, {text}[url] cho link</blockquote>
"""

async def is_valid_user(client, user_id):
    try:
        await client.get_users(user_id)
        return True
    except (PeerIdInvalid, UsernameNotOccupied, UserNotParticipant):
        return False

# Admin cache reload
@app.on_chat_member_updated(filters.group, group=5)
async def admin_cache_func(_, cmu):
    if cmu.old_chat_member and cmu.old_chat_member.promoted_by:
        try:
            admins_in_chat[cmu.chat.id] = {
                "last_updated_at": time(),
                "data": [
                    member.user.id
                    async for member in app.get_chat_members(
                        cmu.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS
                    )
                ],
            }
            LOGGER.info(f"Updated admin cache for {cmu.chat.id} [{cmu.chat.title}]")
        except:
            pass


# Purge CMD
@app.on_cmd("xoanhieu")
@app.adminsOnly("can_change_info")
@use_chat_lang()
async def purge(_, ctx: Message, strings):
    try:
        repliedmsg = ctx.reply_to_message
        await ctx.delete_msg()

        if not repliedmsg:
            return await ctx.reply_msg(strings("purge_no_reply"))

        cmd = ctx.command
        if len(cmd) > 1 and cmd[1].isdigit():
            purge_to = repliedmsg.id + int(cmd[1])
            purge_to = min(purge_to, ctx.id)
        else:
            purge_to = ctx.id

        chat_id = ctx.chat.id
        message_ids = []
        del_total = 0

        for message_id in range(
            repliedmsg.id,
            purge_to,
        ):
            message_ids.append(message_id)

            # Max message deletion limit is 100
            if len(message_ids) == 100:
                await app.delete_messages(
                    chat_id=chat_id,
                    message_ids=message_ids,
                    revoke=True,  # For both sides
                )
                del_total += len(message_ids)
                # To delete more than 100 messages, start again
                message_ids = []

        # Delete if any messages left
        if len(message_ids) > 0:
            await app.delete_messages(
                chat_id=chat_id,
                message_ids=message_ids,
                revoke=True,
            )
            del_total += len(message_ids)
        await ctx.reply_msg(strings("purge_success").format(del_total=del_total))
    except Exception as err:
        await ctx.reply_msg(f"ERROR: {err}")


# Kick members
@app.on_cmd(["sut", "xsut"], self_admin=True, group_only=True)
@app.adminsOnly("can_restrict_members")
@use_chat_lang()
async def kickFunc(client: Client, ctx: Message, strings) -> "Message":
    user_id, reason = await extract_user_and_reason(ctx)
    if not user_id:
        return await ctx.reply_msg(strings("user_not_found"))
    if user_id == client.me.id:
        return await ctx.reply_msg(strings("kick_self_err"))
    if user_id in SUDO:
        return await ctx.reply_msg(strings("kick_sudo_err"))
    if user_id in (await list_admins(ctx.chat.id)):
        return await ctx.reply_msg(strings("kick_admin_err"))
    try:
        user = await app.get_users(user_id)
    except PeerIdInvalid:
        return await ctx.reply_msg(strings("user_not_found"))
    msg = strings("kick_msg").format(
        mention=user.mention,
        id=user.id,
        kicker=ctx.from_user.mention if ctx.from_user else "Anon Admin",
        reasonmsg=reason or "-",
    )
    if ctx.command[0][0] == "x":
        await ctx.reply_to_message.delete_msg()
    try:
        await ctx.chat.ban_member(user_id)
        await ctx.reply_msg(msg)
        await asyncio.sleep(1)
        await ctx.chat.unban_member(user_id)
    except ChatAdminRequired:
        await ctx.reply_msg(strings("no_ban_permission"))
    except Exception as e:
        await ctx.reply_msg(str(e))


@app.on_cmd(["cam", "xcam", "tcam"], self_admin=True, group_only=True)
@app.adminsOnly("can_restrict_members")
@use_chat_lang()
async def banFunc(client, message, strings):
    try:
        user_id, reason = await extract_user_and_reason(message, sender_chat=True)
    except (UsernameNotOccupied, PeerIdInvalid):
        return await message.reply_msg("ID sai hoặc người dùng không tồn tại.")

    if not user_id:
        return await message.reply_text(strings("user_not_found"))
    
    # Kiểm tra user_id hợp lệ
    if not await is_valid_user(client, user_id):
        return await message.reply_text("ID sai hoặc người dùng không tồn tại.")

    if user_id == client.me.id:
        return await message.reply_text(strings("ban_self_err"))
    if user_id in SUDO:
        return await message.reply_text(strings("ban_sudo_err"))
    if user_id in (await list_admins(message.chat.id)):
        return await message.reply_text(strings("ban_admin_err"))

    try:
        mention = (await app.get_users(user_id)).mention
    except (PeerIdInvalid, UsernameNotOccupied):
        return await message.reply_text("ID sai hoặc người dùng không tồn tại.")
    except IndexError:
        mention = (
            message.reply_to_message.sender_chat.title
            if message.reply_to_message
            else "Anon"
        )

    msg = strings("ban_msg").format(
        mention=mention,
        id=user_id,
        banner=message.from_user.mention if message.from_user else "Anon",
    )

    # Xử lý lệnh xcam: Chỉ xóa tin nhắn nếu có reply, vẫn cấm dù không có reply
    if message.command[0] == "xcam":
        if message.reply_to_message:  # Kiểm tra xem có tin nhắn trả lời không
            try:
                await message.reply_to_message.delete()
            except Exception as e:
                await message.reply_msg(f"Không thể xóa tin nhắn: {str(e)}")
        if reason:  # Thêm lý do nếu được cung cấp
            msg += strings("banned_reason").format(reas=reason)
        try:
            await message.chat.ban_member(user_id)
            await message.reply_msg(msg, reply_markup=ikb({"🚨 Bỏ Cấm 🚨": f"bocam_{user_id}"}))
        except ChatAdminRequired:
            await message.reply("Xin hãy cho tôi quyền cấm thành viên..!!!")
        except Exception as e:
            await message.reply_msg(str(e))
        return

    # Xử lý lệnh tcam: Cấm có thời hạn và lý do
    if message.command[0] == "tcam":
        if not reason:
            return await message.reply_text("Vui lòng cung cấp thời gian cấm!")
        split = reason.split(None, 1)
        time_value = split[0]
        temp_reason = split[1] if len(split) > 1 else ""
        temp_ban = await time_converter(message, time_value)
        msg += strings("banner_time").format(val=time_value)
        if temp_reason:
            msg += strings("banned_reason").format(reas=temp_reason)
        try:
            if len(time_value[:-1]) < 3:
                await message.chat.ban_member(user_id, until_date=temp_ban)
                await message.reply_text(msg)
            else:
                await message.reply_text(strings("no_more_99"))
        except AttributeError:
            pass
        return

    # Xử lý lệnh cam: Cấm vĩnh viễn và thêm lý do nếu có
    if reason:
        msg += strings("banned_reason").format(reas=reason)
    keyboard = ikb({"🚨 Bỏ Cấm 🚨": f"bocam_{user_id}"})
    try:
        await message.chat.ban_member(user_id)
        await message.reply_msg(msg, reply_markup=keyboard)
    except ChatAdminRequired:
        await message.reply("Xin hãy cho tôi quyền cấm thành viên..!!!")
    except Exception as e:
        await message.reply_msg(str(e))

# Unban members
@app.on_cmd("bocam", self_admin=True, group_only=True)
@app.adminsOnly("can_restrict_members")
@use_chat_lang()
async def unban_func(_, message, strings):
    reply = message.reply_to_message

    if reply and reply.sender_chat and reply.sender_chat != message.chat.id:
        return await message.reply_text(strings("unban_channel_err"))

    if len(message.command) == 2:
        user = message.text.split(None, 1)[1]
    elif len(message.command) == 1 and reply:
        user = message.reply_to_message.from_user.id
    else:
        return await message.reply_msg(strings("give_unban_user"))

    try:
        user_id = int(user) if user.isdigit() else user
        if not await is_valid_user(app, user_id):
            return await message.reply_msg("ID sai hoặc người dùng không tồn tại.")
        await message.chat.unban_member(user_id)
        umention = (await app.get_users(user_id)).mention
        await message.reply_msg(strings("unban_success").format(umention=umention))
    except (PeerIdInvalid, UsernameNotOccupied):
        await message.reply_msg("ID sai hoặc người dùng không tồn tại.")
    except ChatAdminRequired:
        await message.reply("Xin hãy cho tôi quyền bỏ cấm thành viên..!!!")
    except Exception as e:
        await message.reply_msg(str(e))

# Ban users listed in a message
@app.on_message(
    filters.user(SUDO) & filters.command("camds", COMMAND_HANDLER) & filters.group
)
@use_chat_lang()
async def list_ban_(c, message, strings):
    userid, msglink_reason = await extract_user_and_reason(message)
    if not userid or not msglink_reason:
        return await message.reply_text(strings("give_idban_with_msg_link"))
    if len(msglink_reason.split(" ")) == 1:  # message link included with the reason
        return await message.reply_text(strings("give_reason_list_ban"))
    # seperate messge link from reason
    lreason = msglink_reason.split()
    messagelink, reason = lreason[0], " ".join(lreason[1:])

    if not re.search(
        r"(https?://)?t(elegram)?\.me/\w+/\d+", messagelink
    ):  # validate link
        return await message.reply_text(strings("invalid_tg_link"))

    if userid == c.me.id:
        return await message.reply_text(strings("ban_self_err"))
    if userid in SUDO:
        return await message.reply_text(strings("ban_sudo_err"))
    splitted = messagelink.split("/")
    uname, mid = splitted[-2], int(splitted[-1])
    m = await message.reply_text(strings("multiple_ban_progress"))
    try:
        msgtext = (await app.get_messages(uname, mid)).text
        gusernames = re.findall(r"@\w+", msgtext)
    except:
        return await m.edit_text(strings("failed_get_uname"))
    count = 0
    for username in gusernames:
        try:
            await app.ban_chat_member(username.strip("@"), userid)
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except:
            continue
        count += 1
    mention = (await app.get_users(userid)).mention

    msg = strings("listban_msg").format(
        mention=mention,
        uid=userid,
        frus=message.from_user.mention,
        ct=count,
        reas=reason,
    )
    await m.edit_text(msg)


# Unban users listed in a message
@app.on_message(
    filters.user(SUDO) & filters.command("bocamds", COMMAND_HANDLER) & filters.group
)
@use_chat_lang()
async def list_unban(_, message, strings):
    userid, msglink = await extract_user_and_reason(message)
    if not userid or not msglink:
        return await message.reply_text(strings("give_idunban_with_msg_link"))

    if not re.search(r"(https?://)?t(elegram)?\.me/\w+/\d+", msglink):  # validate link
        return await message.reply_text(strings("invalid_tg_link"))

    splitted = msglink.split("/")
    uname, mid = splitted[-2], int(splitted[-1])
    m = await message.reply_text(strings("multiple_unban_progress"))
    try:
        msgtext = (await app.get_messages(uname, mid)).text
        gusernames = re.findall(r"@\w+", msgtext)
    except:
        return await m.edit_text(strings("failed_get_uname"))
    count = 0
    for username in gusernames:
        try:
            await app.unban_chat_member(username.strip("@"), userid)
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except:
            continue
        count += 1
    mention = (await app.get_users(userid)).mention
    msg = strings("listunban_msg").format(
        mention=mention, uid=userid, frus=message.from_user.mention, ct=count
    )
    await m.edit_text(msg)


# Delete messages
@app.on_cmd("xoa", group_only=True)
@app.adminsOnly("can_change_info")
@use_chat_lang()
async def deleteFunc(_, message, strings):
    if not message.reply_to_message:
        return await message.reply_text(strings("delete_no_reply"))
    try:
        await message.reply_to_message.delete()
        await message.delete()
    except:
        await message.reply(strings("no_delete_perm"))


# Promote Members
@app.on_cmd(["thangcap", "fullthangcap"], self_admin=True, group_only=True)
@app.adminsOnly("can_promote_members")
@use_chat_lang()
async def promoteFunc(client, message, strings):
    try:
        user_id = await extract_user(message)
        umention = (await client.get_users(user_id)).mention
    except:
        return await message.reply(strings("invalid_id_uname"))
    if not user_id:
        return await message.reply_text(strings("user_not_found"))
    bot = (await client.get_chat_member(message.chat.id, client.me.id)).privileges
    if user_id == client.me.id:
        return await message.reply_msg(strings("promote_self_err"))
    if not bot:
        return await message.reply_msg("Tôi không phải là quản trị viên trong cuộc trò chuyện này.")
    if not bot.can_promote_members:
        return await message.reply_msg(strings("no_promote_perm"))
    try:
        if message.command[0][0] == "f":
            await message.chat.promote_member(
                user_id=user_id,
                privileges=ChatPrivileges(
                    can_change_info=bot.can_change_info,
                    can_invite_users=bot.can_invite_users,
                    can_delete_messages=bot.can_delete_messages,
                    can_restrict_members=bot.can_restrict_members,
                    can_pin_messages=bot.can_pin_messages,
                    can_promote_members=bot.can_promote_members,
                    can_manage_chat=bot.can_manage_chat,
                    can_manage_video_chats=bot.can_manage_video_chats,
                ),
            )
            return await message.reply_text(
                strings("full_promote").format(umention=umention)
            )

        await message.chat.promote_member(
            user_id=user_id,
            privileges=ChatPrivileges(
                can_change_info=False,
                can_invite_users=bot.can_invite_users,
                can_delete_messages=bot.can_delete_messages,
                can_restrict_members=bot.can_restrict_members,
                can_pin_messages=bot.can_pin_messages,
                can_promote_members=False,
                can_manage_chat=bot.can_manage_chat,
                can_manage_video_chats=bot.can_manage_video_chats,
            ),
        )
        await message.reply_msg(strings("normal_promote").format(umention=umention))
    except Exception as err:
        await message.reply_msg(err)


# Demote Member
@app.on_cmd("hacap", self_admin=True, group_only=True)
@app.adminsOnly("can_restrict_members")
@use_chat_lang()
async def demote(client, message, strings):
    user_id = await extract_user(message)
    if not user_id:
        return await message.reply_text(strings("user_not_found"))
    if user_id == client.me.id:
        return await message.reply_text(strings("demote_self_err"))
    if user_id in SUDO:
        return await message.reply_text(strings("demote_sudo_err"))
    try:
        await message.chat.promote_member(
            user_id=user_id,
            privileges=ChatPrivileges(
                can_change_info=False,
                can_invite_users=False,
                can_delete_messages=False,
                can_restrict_members=False,
                can_pin_messages=False,
                can_promote_members=False,
                can_manage_chat=False,
                can_manage_video_chats=False,
            ),
        )
        umention = (await app.get_users(user_id)).mention
        await message.reply_text(f"Đã hạ cấp! {umention}")
    except ChatAdminRequired:
        await message.reply("Xin hãy cho phép hạ cấp thành viên..")
    except Exception as e:
        await message.reply_msg(str(e))


# Pin Messages
@app.on_cmd(["ghim", "boghim"])
@app.adminsOnly("can_pin_messages")
@use_chat_lang()
async def pin(_, message, strings):
    if not message.reply_to_message:
        return await message.reply_text(strings("pin_no_reply"))
    r = message.reply_to_message
    try:
        if message.command[0][0] == "b":
            await r.unpin()
            return await message.reply_text(
                strings("unpin_success").format(link=r.link),
                disable_web_page_preview=True,
            )
        await r.pin(disable_notification=True)
        await message.reply(
            strings("pin_success").format(link=r.link),
            disable_web_page_preview=True,
        )
    except ChatAdminRequired:
        await message.reply(
            strings("pin_no_perm"),
            disable_web_page_preview=True,
        )
    except Exception as e:
        await message.reply_msg(str(e))


# Mute members
@app.on_cmd(["immom", "timmom"], self_admin=True, group_only=True)
@app.adminsOnly("can_restrict_members")
@use_chat_lang()
async def mute(client, message, strings):
    try:
        user_id, reason = await extract_user_and_reason(message)
    except (UsernameNotOccupied, PeerIdInvalid):
        return await message.reply("ID sai hoặc người dùng không tồn tại.")
    
    if not user_id:
        return await message.reply_text(strings("user_not_found"))
    
    # Kiểm tra user_id hợp lệ
    if not await is_valid_user(client, user_id):
        return await message.reply_text("ID sai hoặc người dùng không tồn tại.")

    if user_id == client.me.id:
        return await message.reply_text(strings("mute_self_err"))
    if user_id in SUDO:
        return await message.reply_text(strings("mute_sudo_err"))
    if user_id in (await list_admins(message.chat.id)):
        return await message.reply_text(strings("mute_admin_err"))
    
    mention = (await app.get_users(user_id)).mention
    keyboard = ikb({"🚨 Bỏ Im Mồm 🚨": f"boimmom_{user_id}"})
    msg = strings("mute_msg").format(
        mention=mention,
        muter=message.from_user.mention if message.from_user else "Anon",
    )
    
    if message.command[0] == "timmom":
        split = reason.split(None, 1)
        time_value = split[0]
        temp_reason = split[1] if len(split) > 1 else ""
        temp_mute = await time_converter(message, time_value)
        msg += strings("muted_time").format(val=time_value)
        if temp_reason:
            msg += strings("banned_reason").format(reas=temp_reason)
        try:
            if len(time_value[:-1]) < 3:
                await message.chat.restrict_member(
                    user_id,
                    permissions=ChatPermissions(all_perms=False),
                    until_date=temp_mute,
                )
                await message.reply_text(msg, reply_markup=keyboard)
            else:
                await message.reply_text(strings("no_more_99"))
        except AttributeError:
            pass
        return
    
    if reason:
        msg += strings("banned_reason").format(reas=reason)
    try:
        await message.chat.restrict_member(
            user_id, permissions=ChatPermissions(all_perms=False)
        )
        await message.reply_text(msg, reply_markup=keyboard)
    except Exception as e:
        await message.reply_msg(str(e))

# Unmute members
@app.on_cmd("boimmom", self_admin=True, group_only=True)
@app.adminsOnly("can_restrict_members")
@use_chat_lang()
async def unmute(_, message, strings):
    user_id = await extract_user(message)
    if not user_id:
        return await message.reply_text(strings("user_not_found"))
    
    if not await is_valid_user(app, user_id):
        return await message.reply_text("ID sai hoặc người dùng không tồn tại.")
    
    try:
        await message.chat.unban_member(user_id)
        umention = (await app.get_users(user_id)).mention
        await message.reply_msg(strings("unmute_msg").format(umention=umention))
    except (PeerIdInvalid, UsernameNotOccupied):
        await message.reply_msg("ID sai hoặc người dùng không tồn tại.")
    except Exception as e:
        await message.reply_msg(str(e))

@app.on_cmd(["canhbao", "xcanhbao"], self_admin=True, group_only=True)
@app.adminsOnly("can_restrict_members")
@use_chat_lang()
async def warn_user(client, message, strings):
    try:
        user_id, reason = await extract_user_and_reason(message)
    except (UsernameNotOccupied, PeerIdInvalid):
        return await message.reply_msg("ID sai hoặc người dùng không tồn tại.")
    
    chat_id = message.chat.id
    if not user_id:
        return await message.reply_text(strings("user_not_found"))
    
    # Kiểm tra user_id hợp lệ
    if not await is_valid_user(client, user_id):
        return await message.reply_text("ID sai hoặc người dùng không tồn tại.")

    if user_id == client.me.id:
        return await message.reply_text(strings("warn_self_err"))
    if user_id in SUDO:
        return await message.reply_text(strings("warn_sudo_err"))
    if user_id in (await list_admins(chat_id)):
        return await message.reply_text(strings("warn_admin_err"))
    
    user, warns = await asyncio.gather(
        app.get_users(user_id),
        get_warn(chat_id, await int_to_alpha(user_id)),
    )
    mention = user.mention
    keyboard = ikb({strings("rm_warn_btn"): f"gocanhbao_{user_id}"})
    warns = warns["warns"] if warns else 0
    
    if message.command[0][0] == "x":
        await message.reply_to_message.delete()
    
    if warns >= 2:
        await message.chat.ban_member(user_id)
        await message.reply_text(strings("exceed_warn_msg").format(mention=mention))
        await remove_warns(chat_id, await int_to_alpha(user_id))
    else:
        warn = {"warns": warns + 1}
        msg = strings("warn_msg").format(
            mention=mention,
            warner=message.from_user.mention if message.from_user else "Anon",
            reas=reason or "Không có lý do nào được cung cấp.",
            twarn=warns + 1,
        )
        await message.reply_text(msg, reply_markup=keyboard)
        await add_warn(chat_id, await int_to_alpha(user_id), warn)


@app.on_callback_query(filters.regex("gocanhbao_"))
@use_chat_lang()
async def remove_warning(_, cq, strings):
    from_user = cq.from_user
    chat_id = cq.message.chat.id
    permissions = await member_permissions(chat_id, from_user.id)
    permission = "can_restrict_members"
    if permission not in permissions:
        return await cq.answer(
            strings("no_permission_error").format(permissions=permission),
            show_alert=True,
        )
    user_id = int(cq.data.split("_")[1])
    warns = await get_warn(chat_id, await int_to_alpha(user_id))
    if warns:
        warns = warns["warns"]
    if not warns or warns == 0:
        return await cq.answer(
            strings("user_no_warn").format(
                mention=cq.message.reply_to_message.from_user.id
            )
        )
    warn = {"warns": warns - 1}
    await add_warn(chat_id, await int_to_alpha(user_id), warn)
    text = cq.message.text.markdown
    text = f"~~{text}~~\n\n"
    text += strings("unwarn_msg").format(mention=from_user.mention)
    await cq.message.edit(text)


@app.on_callback_query(filters.regex("boimmom_"))
@use_chat_lang()
async def unmute_user(_, cq, strings):
    from_user = cq.from_user
    chat_id = cq.message.chat.id
    permissions = await member_permissions(chat_id, from_user.id)
    permission = "can_restrict_members"
    if permission not in permissions:
        return await cq.answer(
            strings("no_permission_error").format(permissions=permission),
            show_alert=True,
        )
    user_id = int(cq.data.split("_")[1])
    text = cq.message.text.markdown
    text = f"~~{text}~~\n\n"
    text += strings("rmmute_msg").format(mention=from_user.mention)
    try:
        await cq.message.chat.unban_member(user_id)
        await cq.message.edit(text)
    except Exception as e:
        await cq.answer(str(e))


@app.on_callback_query(filters.regex("bocam_"))
@use_chat_lang()
async def unban_user(_, cq, strings):
    from_user = cq.from_user
    chat_id = cq.message.chat.id
    permissions = await member_permissions(chat_id, from_user.id)
    permission = "can_restrict_members"
    if permission not in permissions:
        return await cq.answer(
            strings("no_permission_error").format(permissions=permission),
            show_alert=True,
        )
    user_id = int(cq.data.split("_")[1])
    text = cq.message.text.markdown
    text = f"~~{text}~~\n\n"
    text += strings("unban_msg").format(mention=from_user.mention)
    try:
        await cq.message.chat.unban_member(user_id)
        await cq.message.edit(text)
    except Exception as e:
        await cq.answer(str(e))


# Remove Warn
@app.on_cmd("gocanhbao", self_admin=True, group_only=True)
@app.adminsOnly("can_restrict_members")
@use_chat_lang()
async def remove_warnings(_, message, strings):
    if not message.reply_to_message:
        return await message.reply_text(strings("reply_to_rm_warn"))
    user_id = message.reply_to_message.from_user.id
    mention = message.reply_to_message.from_user.mention
    chat_id = message.chat.id
    warns = await get_warn(chat_id, await int_to_alpha(user_id))
    if warns:
        warns = warns["warns"]
    if warns == 0 or not warns:
        await message.reply_text(strings("user_no_warn").format(mention=mention))
    else:
        await remove_warns(chat_id, await int_to_alpha(user_id))
        await message.reply_text(strings("rmwarn_msg").format(mention=mention))


# Warns
@app.on_cmd("xemcanhbao", group_only=True)
@use_chat_lang()
async def check_warns(_, message, strings):
    if not message.from_user:
        return
    user_id = await extract_user(message)
    if not user_id:
        return await message.reply_text(strings("user_not_found"))
    warns = await get_warn(message.chat.id, await int_to_alpha(user_id))
    mention = (await app.get_users(user_id)).mention
    if warns:
        warns = warns["warns"]
    else:
        return await message.reply_text(strings("user_no_warn").format(mention=mention))
    return await message.reply_text(
        strings("ch_warn_msg").format(mention=mention, warns=warns)
    )


# Report User in Group
@app.on_message(
    (
        filters.command("baocao", COMMAND_HANDLER)
        | filters.command(["admins", "admin"], prefixes="@")
    )
    & filters.group
)
@capture_err
@use_chat_lang()
async def report_user(_, ctx: Message, strings) -> "Message":
    if len(ctx.text.split()) <= 1 and not ctx.reply_to_message:
        return await ctx.reply_msg(strings("report_no_reply"))
    reply = ctx.reply_to_message if ctx.reply_to_message else ctx
    reply_id = reply.from_user.id if reply.from_user else reply.sender_chat.id
    user_id = ctx.from_user.id if ctx.from_user else ctx.sender_chat.id
    if reply_id == user_id:
        return await ctx.reply_msg(strings("report_self_err"))

    list_of_admins = await list_admins(ctx.chat.id)
    linked_chat = (await app.get_chat(ctx.chat.id)).linked_chat
    if linked_chat is None:
        if reply_id in list_of_admins or reply_id == ctx.chat.id:
            return await ctx.reply_msg(strings("reported_is_admin"))
    elif (
        reply_id in list_of_admins
        or reply_id == ctx.chat.id
        or reply_id == linked_chat.id
    ):
        return await ctx.reply_msg(strings("reported_is_admin"))
    user_mention = (
        reply.from_user.mention if reply.from_user else reply.sender_chat.title
    )
    text = strings("report_msg").format(user_mention=user_mention)
    admin_data = [
        m
        async for m in app.get_chat_members(
            ctx.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS
        )
    ]
    for admin in admin_data:
        if admin.user.is_bot or admin.user.is_deleted:
            # return bots or deleted admins
            continue
        text += f"<a href='tg://user?id={admin.user.id}'>\u2063</a>"
    await reply.reply_msg(text)


@app.on_cmd("doiten", self_admin=True, group_only=True)
@app.adminsOnly("can_change_info")
async def set_chat_title(_, ctx: Message):
    if len(ctx.command) < 2:
        return await ctx.reply_text(f"**Usage:**\n/{ctx.command[0]} NEW NAME")
    old_title = ctx.chat.title
    new_title = ctx.text.split(None, 1)[1]
    try:
        await ctx.chat.set_title(new_title)
        await ctx.reply_text(
            f"Đã thay đổi thành công tiêu đề nhóm từ {old_title} thành {new_title}"
        )
    except Exception as e:
        await ctx.reply_msg(str(e))

@app.on_cmd("doianh", self_admin=True, group_only=True)
@app.adminsOnly("can_change_info")
async def set_chat_photo(_, ctx: Message):
    reply = ctx.reply_to_message

    if not reply:
        return await ctx.reply_text("Trả lời một bức ảnh để đặt nó thành chat_photo")

    file = reply.document or reply.photo
    if not file:
        return await ctx.reply_text(
            "Trả lời ảnh hoặc tài liệu để đặt nó thành chat_photo"
        )

    if file.file_size > 5000000:
        return await ctx.reply("Kích thước tập tin quá lớn.")

    photo = await reply.download()
    try:
        await ctx.chat.set_photo(photo=photo)
        await ctx.reply_text("Đã thay đổi ảnh nhóm thành công")
    except Exception as err:
        await ctx.reply(f"Không thay đổi được ảnh nhóm. LỖI: {err}")
    os.remove(photo)


@app.on_message(filters.group & filters.command("tagall", COMMAND_HANDLER))
async def mentionall(app: Client, msg: Message):
    user = await msg.chat.get_member(msg.from_user.id)
    if user.status in (
        enums.ChatMemberStatus.OWNER,
        enums.ChatMemberStatus.ADMINISTRATOR,
    ):
        total = []
        async for member in app.get_chat_members(msg.chat.id):
            member: ChatMember
            if member.user.username:
                total.append(f"@{member.user.username}")
            else:
                total.append(member.user.mention())

        NUM = 4
        for i in range(0, len(total), NUM):
            message = " ".join(total[i : i + NUM])
            await app.send_message(
                msg.chat.id, message, message_thread_id=msg.message_thread_id
            )
    else:
        await app.send_message(
            msg.chat.id, "Chỉ có quản trị viên mới có thể làm điều đó !", reply_to_message_id=msg.id
        )
