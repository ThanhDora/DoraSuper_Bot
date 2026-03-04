import os
import re
import textwrap
import time
import asyncio
import logging
from logging import getLogger

from datetime import datetime, timedelta

from PIL import Image, ImageChops, ImageDraw, ImageFont
from pyrogram import Client, enums, filters
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.errors import (
    ChatAdminRequired,
    ChatSendPhotosForbidden,
    ChatWriteForbidden,
    MessageTooLong,
    RPCError,
    PeerIdInvalid,
)
from pyrogram.types import ChatMemberUpdated, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database.chat_ban_db import get_chat_ban_until
from database.chat_mute_db import get_chat_mute_until
from database.gban_db import is_gbanned_user
from database.greetings_db import (
    is_welcome, toggle_welcome, set_custom_welcome, get_custom_welcome,
    is_goodbye, toggle_goodbye, set_custom_goodbye, get_custom_goodbye,
    is_ban_on_leave, toggle_ban_on_leave
)
from database.report_link_db import (
    is_report_link_enabled,
    toggle_report_link,
    set_excluded_links,
    get_excluded_links
)
from database.users_chats_db import db, peers_db
from dorasuper import BOT_USERNAME, app
from dorasuper.core.decorator import asyncify, capture_err
from dorasuper.core.decorator.permissions import (
    admins_in_chat,
    list_admins,
    member_permissions,
)
from dorasuper.helper import fetch, use_chat_lang
from dorasuper.helper.emoji_fmt import EMOJI_FMT
from dorasuper.vars import COMMAND_HANDLER, SUDO, SUPPORT_CHAT
from utils import temp
from dorasuper.emoji import E_BACK, E_CROSS, E_ERROR, E_HEART, E_LOADING, E_NOTE, E_OTO, E_SUCCESS, E_USER, E_VIP, E_WELCOME, E_WELCOME1, E_WELCOME2


LOGGER = getLogger("DoraSuper")

def extract_links(text: str) -> list:
    # Regex cải tiến để bắt các URL
    url_pattern = r'(?:(?:https?://|www\.|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})(?:[^\s<>"]+)?)'
    return re.findall(url_pattern, text, re.IGNORECASE)

async def is_link_excluded(link: str, excluded_links: list) -> bool:
    # Kiểm tra xem link có nằm trong danh sách loại trừ không
    for excluded in excluded_links:
        if excluded.lower() in link.lower():
            return True
    return False
    
def circle(pfp, size=(215, 215)):
    pfp = pfp.resize(size, Image.LANCZOS).convert("RGBA")
    bigsize = (pfp.size[0] * 3, pfp.size[1] * 3)
    mask = Image.new("L", bigsize, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + bigsize, fill=255)
    mask = mask.resize(pfp.size, Image.LANCZOS)
    mask = ImageChops.darker(mask, pfp.split()[-1])
    pfp.putalpha(mask)
    return pfp

def draw_multiple_line_text(image, text, font, text_start_height):
    draw = ImageDraw.Draw(image)
    image_width, _ = image.size
    y_text = text_start_height
    lines = textwrap.wrap(text, width=50)
    for line in lines:
        text_bbox = font.getbbox(line)
        (left, top, right, bottom) = text_bbox
        line_width = abs(right - left)
        line_height = abs(top - bottom)
        draw.text(
            ((image_width - line_width) / 2, y_text), line, font=font, fill="black"
        )
        y_text += line_height

@asyncify
def welcomepic(pic, user, chat, id, strings):
    background = Image.open("assets/bg.png")
    background = background.resize((1024, 500), Image.LANCZOS)
    pfp = Image.open(pic).convert("RGBA")
    pfp = circle(pfp)
    pfp = pfp.resize((450, 450))
    # font = ImageFont.truetype("assets/MarkaziText-Bold.ttf", 37)
    # member_text = strings("welcpic_msg").format(userr=user, id=id)
    # draw_multiple_line_text(background, member_text, font, 395)
    # draw_multiple_line_text(background, chat, font, 47)
    # ImageDraw.Draw(background).text(
    #     (530, 460),
    #     f"Lời chào của @{BOT_USERNAME}",
    #     font=ImageFont.truetype("assets/MarkaziText-Bold.ttf", 28),
    #     size=20,
    #     align="right",
    # )
    background.paste(pfp, (285, 30), pfp)
    background.save(f"downloads/welcome#{id}.png")
    return f"downloads/welcome#{id}.png"

@app.on_chat_member_updated(filters.group, group=4)
@use_chat_lang()
async def member_has_joined_or_left(c: Client, member: ChatMemberUpdated, strings):
    # Xử lý khi người dùng rời nhóm
    if not member.new_chat_member:
        if member.old_chat_member and member.old_chat_member.status == CMS.MEMBER:
            user_left = member.old_chat_member.user
            await db.log_member_leave(member.chat.id, user_left.id)
            # Tin nhắn tạm biệt
            if await is_goodbye(member.chat.id):
                try:
                    mention = f"<a href='tg://user?id={user_left.id}'>{user_left.first_name}</a>"
                    custom_msg, buttons = await get_custom_goodbye(member.chat.id)
                    if custom_msg:
                        goodbye_text = custom_msg.format(
                            mention=mention,
                            first_name=user_left.first_name or "",
                            chat_title=member.chat.title or "",
                        )
                    else:
                        goodbye_text = f"{E_BACK} Tạm biệt {mention}! Hẹn gặp lại."
                    inline_buttons = []
                    if buttons:
                        current_row = []
                        for btn in buttons:
                            button = InlineKeyboardButton(text=btn["text"], url=btn["url"])
                            current_row.append(button)
                            if len(current_row) == 2:
                                inline_buttons.append(current_row)
                                current_row = []
                        if current_row:
                            inline_buttons.append(current_row)
                    reply_markup = InlineKeyboardMarkup(inline_buttons) if inline_buttons else None
                    await c.send_message(
                        member.chat.id,
                        goodbye_text,
                        reply_markup=reply_markup,
                        parse_mode=enums.ParseMode.HTML,
                    )
                except Exception as e:
                    LOGGER.info("Goodbye message error: %s", e)
            # Xử lý cấm tự động khi rời nhóm
            if await is_ban_on_leave(member.chat.id):
                try:
                    await c.ban_chat_member(member.chat.id, user_left.id)
                    await c.send_message(
                        member.chat.id,
                        f"{E_CROSS} Người dùng <a href='tg://user?id={user_left.id}'>{user_left.first_name}</a> đã bị cấm vì tự ý rời nhóm.",
                        parse_mode=enums.ParseMode.HTML,
                    )
                except Exception as e:
                    LOGGER.info(f"Không thể cấm người dùng {user_left.id}: {e}")
        return

    # Xử lý khi người dùng tham gia nhóm
    user = member.new_chat_member.user
    new_status = member.new_chat_member.status
    # Chỉ xử lý khi user thực sự tham gia (MEMBER), tránh trùng khi Telegram gửi update cấm
    if new_status != CMS.MEMBER:
        return
    # Tự động kick/ban nếu user bị gban (cấm toàn cầu) — mời lại vẫn bị đá
    if await is_gbanned_user(user.id):
        try:
            await c.ban_chat_member(member.chat.id, user.id)
            await c.send_message(
                member.chat.id,
                f"{E_CROSS} Người dùng <a href='tg://user?id={user.id}'>{user.first_name or 'N/A'}</a> đang bị cấm toàn cầu (gban), đã bị loại khỏi nhóm.",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as e:
            LOGGER.info("Không thể kick user gban %s: %s", user.id, e)
        return
    # Tự động cấm lại nếu user đang trong thời gian bị cấm (cam vĩnh viễn hoặc tcam) — mời lại vẫn bị ban
    until_ban_ts = await get_chat_ban_until(member.chat.id, user.id)
    if until_ban_ts is not None:
        try:
            until_date = datetime.fromtimestamp(until_ban_ts) if until_ban_ts > 0 else None
            await c.ban_chat_member(member.chat.id, user.id, until_date=until_date)
            await c.send_message(
                member.chat.id,
                f"{E_CROSS} Người dùng <a href='tg://user?id={user.id}'>{user.first_name}</a> đang trong thời gian bị cấm, không thể tham gia lại.",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as e:
            LOGGER.info("Không thể cấm lại user %s: %s", user.id, e)
        return

    # Tự động tắt mic lại nếu user đang trong thời gian bị mute (immom/timmom) — mời lại vẫn bị restrict
    until_ts = await get_chat_mute_until(member.chat.id, user.id)
    if until_ts is not None:
        try:
            until_date = datetime.fromtimestamp(until_ts) if until_ts > 0 else None
            await c.restrict_chat_member(
                member.chat.id,
                user.id,
                ChatPermissions(all_perms=False),
                until_date=until_date,
            )
            await c.send_message(
                member.chat.id,
                f"{E_NOTE} <a href='tg://user?id={user.id}'>{user.first_name or 'N/A'}</a> đang trong thời gian bị tắt mic, đã áp dụng lại.",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception as e:
            LOGGER.info("Không thể restrict lại user mute %s: %s", user.id, e)
        return

    # Chào mừng
    if await is_welcome(member.chat.id):
        if user.id in SUDO:
            await c.send_message(member.chat.id, strings("sudo_join_msg").format(**EMOJI_FMT))
            return

        new_status = member.new_chat_member.status
        old_status = member.old_chat_member.status if member.old_chat_member else None

        # Chỉ gửi lời chào nếu người dùng thực sự mới tham gia (từ không phải thành viên sang thành viên)
        if new_status != CMS.MEMBER:
            return
        if old_status in [CMS.MEMBER, CMS.ADMINISTRATOR, CMS.OWNER]:
            return  # Bỏ qua nếu người dùng đã là thành viên hoặc quản trị viên trước đó

        await db.log_member_join(member.chat.id, user.id)
        member_history = await db.get_member_history(member.chat.id, user.id)
        join_count = member_history.get("join_count", 0)
        first_joined = member_history.get("first_joined")
        last_left = member_history.get("last_left")
        mention = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"

        joined_date = datetime.fromtimestamp(time.time()).strftime("%d/%m/%Y %H:%M:%S")
        first_joined_str = first_joined.strftime("%d/%m/%Y %H:%M:%S") if first_joined and isinstance(first_joined, datetime) else (joined_date if join_count == 1 else "Không rõ")
        last_left_str = last_left.strftime("%d/%m/%Y %H:%M:%S") if last_left and isinstance(last_left, datetime) else "Chưa từng rời"

        custom_message, buttons = await get_custom_welcome(member.chat.id)
        if join_count == 1:
            welcome_text = f"{E_WELCOME} Chào mừng {E_WELCOME1}{mention}{E_WELCOME2} đến với nhóm {member.chat.title}!\n\n⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰\n{custom_message or 'Vui lòng xem nội quy để tránh vi phạm nhé!'}\n{E_OTO}"
        else:
            welcome_text = f"{E_WELCOME} Xin chào {E_WELCOME1}{mention}{E_WELCOME2} đã quay lại nhóm {member.chat.title} lần thứ {join_count}!\n\n⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰⋰\n{custom_message or 'Trước đây bạn đã rời đi nên giờ hãy đọc lại nội quy để tránh vi phạm nhé!'}\n{E_OTO}"

        if (temp.MELCOW).get(f"welcome-{member.chat.id}") is not None:
            try:
                await temp.MELCOW[f"welcome-{member.chat.id}"].delete()
            except:
                pass

        first_name = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        id = user.id
        dc = user.dc_id or "Không rõ"

        try:
            pic = await app.download_media(user.photo.big_file_id, file_name=f"pp{user.id}.png")
        except AttributeError:
            pic = "assets/profilepic.png"

        try:
            welcomeimg = await welcomepic(pic, user.first_name, member.chat.title, user.id, strings)
            if join_count == 1:
                caption = (f"{welcome_text}\n\n"
                          f"<b>Tên thành viên:</b> <code>{first_name}</code>\n"
                          f"<b>Tham gia vào lúc:</b> <code>{joined_date}</code>")
            else:
                caption = (f"{welcome_text}\n\n"
                          f"<b>Tên thành viên:</b> <code>{first_name}</code>\n"
                          f"<b>Tham gia lần đầu:</b> <code>{first_joined_str}</code>\n"
                          f"<b>Lần rời gần nhất:</b> <code>{last_left_str}</code>\n"
                          f"<b>Tham gia lại vào:</b> <code>{joined_date}</code>")

            inline_buttons = []
            current_row = []
            for btn in buttons:
                button = InlineKeyboardButton(text=btn["text"], url=btn["url"])
                current_row.append(button)
                if len(current_row) == 2:
                    inline_buttons.append(current_row)
                    current_row = []
            if current_row:
                inline_buttons.append(current_row)
            reply_markup = InlineKeyboardMarkup(inline_buttons) if inline_buttons else None

            temp.MELCOW[f"welcome-{member.chat.id}"] = await c.send_photo(
                member.chat.id,
                photo=welcomeimg,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML
            )

            try:
                os.remove(f"downloads/welcome#{user.id}.png")
                os.remove(f"downloads/pp{user.id}.png")
            except Exception:
                pass

            await asyncio.sleep(600)
            if (temp.MELCOW).get(f"welcome-{member.chat.id}") is not None:
                try:
                    await temp.MELCOW[f"welcome-{member.chat.id}"].delete()
                    del temp.MELCOW[f"welcome-{member.chat.id}"]
                except:
                    pass

        except Exception as e:
            LOGGER.info(e)
            
# Lệnh bật/tắt chào mừng
@app.on_cmd(["chaomung"], self_admin=True, group_only=True)
@app.adminsOnly("can_change_info")
async def welcome_toggle_handler(client, message):
    is_enabled = await toggle_welcome(message.chat.id)
    await message.reply_msg(
        f"{E_HEART} Tin nhắn chào mừng hiện đã {'bật' if is_enabled else 'tắt'}."
    )

# Lệnh thiết lập tin nhắn chào mừng tùy chỉnh
@app.on_cmd(["tinchaomung"], self_admin=True, group_only=True)
@app.adminsOnly("can_change_info")
async def custom_welcome_handler(c: Client, m: Message):
    suggestion_text = (
        "Vui lòng cung cấp nội dung lời chào tùy chỉnh và các nút (nút không bắt buộc).\n\n"
        "Ví dụ:\n"
        "<code>/tinchaomung Chào mừng bạn đến nhóm chúng tôi! (Tham gia kênh)[https://t.me] (Nội quy)[https://t.me]</code>\n\n"
        "Định dạng: *đậm*, _nghiêng_, __gạch dưới__, `mã`, (tên_nút)[url]"
    )

    if len(m.text.split()) < 2:
        return await m.reply(suggestion_text)

    text = m.text[len("/tinchaomung "):].strip()
    button_pattern = r'\((.*?)\)\[(.*?)\]'
    buttons = re.findall(button_pattern, text)
    custom_message = re.sub(button_pattern, '', text).strip()

    if not custom_message:
        return await m.reply("Vui lòng cung cấp nội dung lời chào!\n\n" + suggestion_text)

    custom_message = re.sub(r'\*(.*?)\*', r'<b>\1</b>', custom_message)
    custom_message = re.sub(r'_(.*?)_', r'<i>\1</i>', custom_message)
    custom_message = re.sub(r'__(.*?)__', r'<u>\1</u>', custom_message)
    custom_message = re.sub(r'`(.*?)`', r'<code>\1</code>', custom_message)

    button_data = [{"text": name.strip(), "url": url.strip()} for name, url in buttons]
    await set_custom_welcome(m.chat.id, custom_message, button_data)

    inline_buttons = []
    current_row = []
    for btn in button_data:
        button = InlineKeyboardButton(text=btn["text"], url=btn["url"])
        current_row.append(button)
        if len(current_row) == 2:
            inline_buttons.append(current_row)
            current_row = []
    if current_row:
        inline_buttons.append(current_row)
    reply_markup = InlineKeyboardMarkup(inline_buttons) if inline_buttons else None

    await m.reply(
        f"Lời chào tùy chỉnh đã được thiết lập:\n\n{custom_message}",
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML
    )

# Lệnh bật/tắt tin nhắn tạm biệt
@app.on_cmd(["tambiet"], self_admin=True, group_only=True)
@app.adminsOnly("can_change_info")
async def goodbye_toggle_handler(client, message):
    is_enabled = await toggle_goodbye(message.chat.id)
    await message.reply_msg(
        f"{E_HEART} Tin nhắn tạm biệt hiện đã {'bật' if is_enabled else 'tắt'}."
    )

# Lệnh thiết lập tin nhắn tạm biệt tùy chỉnh
@app.on_cmd(["tintambiet"], self_admin=True, group_only=True)
@app.adminsOnly("can_change_info")
async def custom_goodbye_handler(c: Client, m: Message):
    suggestion_text = (
        "Vui lòng cung cấp nội dung lời tạm biệt tùy chỉnh và các nút (nút không bắt buộc).\n\n"
        "Ví dụ:\n"
        "<code>/tintambiet Tạm biệt {mention}! Hẹn gặp lại. (Kênh)[https://t.me]</code>\n\n"
        "Biến có thể dùng: <code>{mention}</code>, <code>{first_name}</code>, <code>{chat_title}</code>\n"
        "Định dạng: *đậm*, _nghiêng_, (tên_nút)[url]"
    )

    if len(m.text.split()) < 2:
        return await m.reply(suggestion_text)

    text = m.text[len("/tintambiet "):].strip()
    button_pattern = r'\((.*?)\)\[(.*?)\]'
    buttons = re.findall(button_pattern, text)
    custom_message = re.sub(button_pattern, '', text).strip()

    if not custom_message:
        return await m.reply("Vui lòng cung cấp nội dung lời tạm biệt!\n\n" + suggestion_text)

    custom_message = re.sub(r'\*(.*?)\*', r'<b>\1</b>', custom_message)
    custom_message = re.sub(r'_(.*?)_', r'<i>\1</i>', custom_message)
    custom_message = re.sub(r'__(.*?)__', r'<u>\1</u>', custom_message)
    custom_message = re.sub(r'`(.*?)`', r'<code>\1</code>', custom_message)

    button_data = [{"text": name.strip(), "url": url.strip()} for name, url in buttons]
    await set_custom_goodbye(m.chat.id, custom_message, button_data)

    inline_buttons = []
    current_row = []
    for btn in button_data:
        button = InlineKeyboardButton(text=btn["text"], url=btn["url"])
        current_row.append(button)
        if len(current_row) == 2:
            inline_buttons.append(current_row)
            current_row = []
    if current_row:
        inline_buttons.append(current_row)
    reply_markup = InlineKeyboardMarkup(inline_buttons) if inline_buttons else None

    await m.reply(
        f"Lời tạm biệt tùy chỉnh đã được thiết lập:\n\n{custom_message}",
        reply_markup=reply_markup,
        parse_mode=enums.ParseMode.HTML
    )

# Lệnh bật/tắt cấm tự động khi rời nhóm
@app.on_cmd(["camthoat"], self_admin=True, group_only=True)
@app.adminsOnly("can_restrict_members")
async def ban_on_leave_toggle_handler(client, message):
    is_enabled = await toggle_ban_on_leave(message.chat.id)
    await message.reply_msg(
        f"{E_SUCCESS} Chức năng cấm khi người dùng tự ý rời nhóm hiện đã {'bật' if is_enabled else 'tắt'}."
    )

@app.on_cmd(["baolienket"], self_admin=True, group_only=True)
@app.adminsOnly("can_delete_messages")
async def report_link_toggle_handler(client, message):
    is_enabled = await toggle_report_link(message.chat.id)
    await message.reply_msg(
        f"{E_SUCCESS} Chức năng báo cáo liên kết hiện đã {'bật' if is_enabled else 'tắt'}."
    )
    
@app.on_cmd(["loclienket"], self_admin=True, group_only=True)
@app.adminsOnly("can_delete_messages")
async def set_excluded_links_handler(client, message):
    # Kiểm tra xem chức năng báo cáo link đã bật chưa
    if not await is_report_link_enabled(message.chat.id):
        await message.reply_msg(
            f"{E_ERROR} Vui lòng bật chức năng báo cáo liên kết bằng lệnh /baolienket trước."
        )
        return

    # Lấy danh sách domain từ tham số lệnh
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    
    # Kiểm tra nếu không có tham số
    if not args:
        await message.reply_msg(
            f"{E_ERROR} Vui lòng cung cấp danh sách domain để loại trừ, ví dụ: /loclienket apple.com github.com\n"
            "Hoặc sử dụng /loclienket reset để xóa toàn bộ danh sách loại trừ."
        )
        return

    # Kiểm tra lệnh reset
    if args[0].lower() == "reset":
        await set_excluded_links(message.chat.id, [])  # Xóa danh sách loại trừ
        await message.reply_msg(
            f"{E_SUCCESS} Danh sách domain loại trừ đã được xóa."
        )
        return

    # Lưu danh sách domain loại trừ
    await set_excluded_links(message.chat.id, args)
    await message.reply_msg(
        f"{E_SUCCESS} Danh sách domain loại trừ đã được cập nhật: {', '.join(args)}"
    )
    
@app.on_message(filters.text & filters.group, group=6)
@capture_err
async def handle_links_in_group(client, message: Message):
    chat_id = message.chat.id

    # Kiểm tra xem chức năng báo cáo liên kết đã bật chưa
    if not await is_report_link_enabled(chat_id):
        return

    # Lấy nội dung tin nhắn
    text = (message.text or message.caption or "").strip()
    if not text:
        return

    # Kiểm tra URL
    links = extract_links(text)
    if not links:
        return

    # Lấy danh sách link loại trừ
    excluded_links = await get_excluded_links(chat_id)

    # Kiểm tra từng link
    report_links = []
    for link in links:
        if not await is_link_excluded(link, excluded_links):
            report_links.append(link)

    if not report_links:
        return

    # Kiểm tra xem người gửi có phải admin không
    list_of_admins = await list_admins(chat_id)
    sender_id = message.from_user.id if message.from_user else message.sender_chat.id
    if sender_id in list_of_admins:
        return

    # Tạo thông báo báo cáo
    user_mention = (
        message.from_user.mention if message.from_user else message.sender_chat.title
    )
    text = f"🚨 **Báo cáo:** Người dùng {user_mention} đã gửi liên kết trong nhóm:\n{', '.join(report_links)}\n**Các admin hãy kiểm tra và xử lý nếu cần.**"
    
    # Gửi thông báo cho admin
    admin_data = [
        m
        async for m in app.get_chat_members(
            chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS
        )
    ]
    for admin in admin_data:
        if admin.user.is_bot or admin.user.is_deleted:
            continue
        text += f"<a href='tg://user?id={admin.user.id}'>\u2063</a>"

    await message.reply_msg(text)

@app.on_message(filters.command("leave") & filters.user(SUDO))
async def leave_a_chat(bot, message):
    if len(message.command) == 1:
        return await message.reply(f"{E_ERROR} Cho tôi id trò chuyện")
    chat = message.command[1]
    try:
        chat = int(chat)
    except:
        pass
    try:
        buttons = [
            [InlineKeyboardButton("Hỗ trợ", url=f"https://t.me/{SUPPORT_CHAT}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await bot.send_message(
            chat_id=chat,
            text="<b>Này các bạn, \nÔng chủ tôi đã nói là tôi phải đi rồi! Nếu bạn muốn bổ sung thêm cho bot này, vui lòng liên hệ với chủ sở hữu của bot này.</b>",
            reply_markup=reply_markup,
        )
        await bot.leave_chat(chat)
    except Exception as e:
        await message.reply(f"{E_ERROR} Error - {e}")
        await bot.leave_chat(chat)

@app.on_message(filters.command(["tagid"], COMMAND_HANDLER))
async def tag_by_id(client, message):
    # Kiểm tra xem có nội dung sau lệnh hay không
    if len(message.command) < 2:
        return await message.reply(
            f"{E_ERROR} Vui lòng cung cấp danh sách ID và nội dung.\n"
            "Ví dụ:\n"
            "```\n/tagid 123456789 Người 1 - 987654321 Người 2\n```"
        )
    
    try:
        # Lấy toàn bộ nội dung sau lệnh
        text = " ".join(message.command[1:])
        if not text:
            return await message.reply(f"{E_ERROR} Vui lòng cung cấp danh sách ID và nội dung hợp lệ.")

        # Tách các cặp ID - Nội dung bằng dấu " - "
        parts = text.split(" - ")
        mentions = []
        invalid_ids = []

        # Duyệt qua từng cặp ID - Nội dung
        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Tách ID và nội dung
            try:
                user_id, content = map(str.strip, part.split(" ", 1))
                user_id = int(user_id)

                if user_id <= 0:
                    invalid_ids.append(f"{user_id} (ID không hợp lệ)")
                    continue

                # Kiểm tra xem ID có tồn tại không
                try:
                    await client.get_users(user_id)
                    # Tạo mention nếu ID tồn tại
                    mentions.append(f"[{content}](tg://user?id={user_id})")
                except PeerIdInvalid:
                    invalid_ids.append(f"{user_id} (không tồn tại)")

            except ValueError:
                invalid_ids.append(f"{part} (ID không phải số)")
            except Exception as e:
                LOGGER.error(f"Lỗi khi xử lý ID {part}: {e}")
                invalid_ids.append(f"{part} (lỗi: {str(e)})")

        # Kiểm tra kết quả
        if not mentions:
            return await message.reply(
                f"{E_ERROR} Không có ID hợp lệ để tag.\n"
                f"Danh sách lỗi:\n- " + "\n- ".join(invalid_ids) if invalid_ids else ""
            )

        # Gửi tin nhắn với tất cả mention
        mention_text = " ".join(mentions)
        if invalid_ids:
            mention_text += "\n\nID không hợp lệ hoặc không tồn tại:\n- " + "\n- ".join(invalid_ids)

        await message.reply(
            mention_text,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        LOGGER.error(f"Lỗi khi xử lý lệnh tagid: {e}")
        await message.reply(f"{E_ERROR} Đã xảy ra lỗi: {str(e)}")

@app.on_message(filters.command(["dsadmin"], COMMAND_HANDLER), group=-1)
@capture_err
async def adminlist(_, message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply(f"{E_ERROR} Lệnh này chỉ dành cho nhóm.")
    try:
        msg = await message.reply(
            f"{E_LOADING} Đang lấy danh sách quản trị viên trong {message.chat.title}...",
            parse_mode=enums.ParseMode.HTML,
        )
        administrators = []
        async for m in app.get_chat_members(
            message.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS
        ):
            u = m.user
            name = (u.first_name or "") if u else "Deleted"
            uname = f"@{u.username}" if u and getattr(u, "username", None) else ""
            administrators.append(f"{name} [{uname}]".strip())

        res = "".join(f"• {i}\n" for i in administrators)
        text = (
            f"<b>Admin trong nhóm {message.chat.title}</b> (<code>{message.chat.id}</code>):\n\n{res}"
        )
        await msg.edit_text(text, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        LOGGER.exception("dsadmin error")
        await message.reply(f"{E_ERROR} Lỗi: {str(e)}")

@app.on_message(filters.command(["suttoi"], COMMAND_HANDLER))
@capture_err
async def suttoi(_, message):
    reason = None
    if len(message.text.split()) >= 2:
        reason = message.text.split(None, 1)[1]
    
    # Tạo bàn phím nút
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Đá Tôi", callback_data=f"suttoi_kick|{message.from_user.id}|{reason or ''}"),
                InlineKeyboardButton("Cấm Tôi", callback_data=f"suttoi_ban|{message.from_user.id}|{reason or ''}"),
            ],
            [InlineKeyboardButton("Huỷ", callback_data=f"suttoi_cancel|{message.from_user.id}")]
        ]
    )
    
    # Gửi tin nhắn hỏi với nút
    await message.reply_text(
        f"{E_NOTE} Này {message.from_user.mention}, bạn muốn làm gì? Hãy suy nghĩ kĩ nhé!",
        reply_markup=keyboard
    )


@app.on_callback_query(filters.regex(r"^suttoi_(kick|ban|cancel)"))
async def suttoi_callback(_, callback_query):
    try:
        # Trả lời callback để tránh lỗi
        await callback_query.answer()

        # Tách dữ liệu callback
        parts = callback_query.data.split("|")
        action = parts[0].split("_")[1]  # Lấy hành động (kick, ban, cancel)
        user_id = int(parts[1])          # Lấy user ID
        reason = parts[2] if len(parts) > 2 else None  # Lấy lý do (nếu có)

        # Kiểm tra người bấm có phải là người gửi lệnh không
        if callback_query.from_user.id != user_id:
            await callback_query.answer("Bạn không thể thực hiện thao tác này!", show_alert=True)
            return

        # Xử lý hành động
        if action == "cancel":
            await callback_query.message.edit_text(f"{E_ERROR} Đã huỷ yêu cầu, có lẽ bạn đã suy nghĩ lại.")
        elif action == "kick":
            await callback_query.message.chat.ban_member(user_id)
            await callback_query.message.chat.unban_member(user_id)
            response_text = f"{E_ERROR} Người dùng {callback_query.from_user.mention} đã tự đá mình khỏi nhóm. Có lẽ hắn ta đang thất vọng 😕"
            if reason:
                response_text += f"\n<b>Lý do</b>: {reason}"
            await callback_query.message.edit_text(response_text)
        elif action == "ban":
            await callback_query.message.chat.ban_member(user_id)
            response_text = f"{E_ERROR} Người dùng {callback_query.from_user.mention} đã tự cấm mình khỏi nhóm. Có lẽ hắn ta đang tuyệt vọng 😱"
            if reason:
                response_text += f"\n<b>Lý do</b>: {reason}"
            await callback_query.message.edit_text(response_text)

    except RPCError as ef:
        await callback_query.message.edit_text(f"{E_ERROR} Đã có lỗi xảy ra: {str(ef)}")
    except Exception as err:
        await callback_query.message.edit_text(f"{E_ERROR} LỖI: {err}")
        
@app.on_message(filters.command("users") & filters.user(SUDO))
async def list_users(_, message):
    msg = await message.reply(f"{E_LOADING} Đang lấy danh sách thành viên")
    
    users_cursor = await db.get_all_users()  # Lấy toàn bộ người dùng trong 'userlist'
    gbanned_users_cursor = await db.get_all_gbanned_users()  # Lấy toàn bộ người dùng bị cấm global từ 'gban'
    
    out = ""
    
    # Duyệt qua danh sách userlist
    async for user in users_cursor:
        user_id = user.get('_id')
        reason = user.get('reason', 'Không có lý do nào được cung cấp')
        out += f"{E_USER} User ID: {user_id} -> Lý do: {reason}\n"
    
    # Duyệt qua danh sách gban
    async for user in gbanned_users_cursor:
        user_id = user.get('user_id')
        out += f"{E_USER} User ID: {user_id} -> Lý do: Global ban\n"
    
    if not out.strip():  # Kiểm tra nếu không có dữ liệu từ cả hai collection
        out = f"{E_ERROR} Không có user nào được lưu trong DB."
    
    try:
        await msg.edit_text(out)
    except MessageTooLong:
        with open("users.txt", "w+") as outfile:
            outfile.write(out)
        await message.reply_document("users.txt", caption="Danh sách người dùng bị cấm")
        await msg.delete()


@app.on_message(filters.command("chats") & filters.user(SUDO))
async def list_chats(_, message):
    msg = await message.reply("Đang lấy danh sách trò chuyện")
    chats = await db.get_all_chats()
    out = "Các đoạn chat được lưu trong DB:\n\n"
    async for chat in chats:
        out += f"Tiêu đề: {chat.get('title')} ({chat.get('id')}) "
        if chat["chat_status"]["is_disabled"]:
            out += "( Đã cấm )"
        out += "\n"
    try:
        await msg.edit_text(out)
    except MessageTooLong:
        with open("chats.txt", "w+") as outfile:
            outfile.write(out)
        await message.reply_document("chats.txt", caption="Danh sách trò chuyện")
        await msg.delete_msg()

@app.on_message(filters.command("allusers") & filters.user(SUDO))
async def all_users(_, message):
    msg = await message.reply("Đang lấy toàn bộ dữ liệu người dùng")
    
    # Lấy toàn bộ người dùng từ collection 'peers'
    users_cursor = await peers_db.get_all_peers()
    
    out = "Danh sách người dùng trong DB:\n\n"
    
    async for user in users_cursor:
        user_id = user.get('_id')
        #access_hash = user.get('access_hash')
        #last_update_on = user.get('last_update_on')
        #phone_number = user.get('phone_number', 'Không có')
        user_type = user.get('type', 'Không có')
        username = user.get('username', 'Không có')
        
        out += (f"User ID: {user_id}\n"
            #    f"Access Hash: {access_hash}\n"
            #    f"Last Update On: {last_update_on}\n"
            #    f"Phone Number: {phone_number}\n"
                f"Type: {user_type}\n"
                f"Username: {username}\n\n")
    
    if not out.strip():  # Kiểm tra nếu không có dữ liệu người dùng nào
        out = "Không có dữ liệu người dùng nào trong DB."
    
    try:
        await msg.edit_text(out)
    except MessageTooLong:
        with open("users.txt", "w+") as outfile:
            outfile.write(out)
        await message.reply_document("users.txt", caption="Danh sách toàn bộ người dùng trong DB")
        await msg.delete()