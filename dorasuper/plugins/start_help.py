import re

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import ChatSendPhotosForbidden, ChatWriteForbidden
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from dorasuper import BOT_NAME, BOT_USERNAME, HELPABLE, app
from dorasuper.core.decorator.errors import capture_err
from dorasuper.helper import bot_sys_stats, paginate_modules
from dorasuper.helper.emoji_fmt import EMOJI_FMT
from dorasuper.helper.localization import use_chat_lang
from dorasuper.emoji import E_BOT, E_COFFEE, E_DART, E_LIST, E_MEGAPHONE, E_MSG, E_PARTY, E_USER, E_VIP, E_VN
from dorasuper.vars import COMMAND_HANDLER, THUMB_PATH


def _helpable_keys_sorted():
    return sorted(HELPABLE.keys(), key=lambda k: (getattr(HELPABLE[k], "__MODULE__", None) or ""))


home_keyboard_pm = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(text="Các lệnh sử dụng", callback_data="bot_commands"),
        ],
        [
            InlineKeyboardButton(text="Liên hệ admin", url="https://t.me/thanhdora"),
        ],
        [
            InlineKeyboardButton(
                text="Thêm tôi vào nhóm",
                url=f"http://t.me/{BOT_USERNAME}?startgroup=new",
            )
        ],
    ]
)

home_text_pm = f"Chào bạn! Tôi là {BOT_NAME}{E_VIP}. Tôi có nhiều tính năng hữu ích cho bạn, hãy thêm tôi vào nhóm của bạn nếu muốn.\n\nNếu bạn muốn tặng cà phê cho chủ sở hữu của tôi, bạn có thể gửi lệnh /donate để biết thêm thông tin. Tôi chỉ hỗ trợ Tiếng Việt {E_VN}"

keyboard = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(text="Các lệnh sử dụng", url=f"t.me/{BOT_USERNAME}?start=help"),
        ],
        [
            InlineKeyboardButton(text="Liên hệ admin", url="https://t.me/thanhdora"),
        ],
    ]
)


@app.on_message(filters.command("start", COMMAND_HANDLER), group=-1)
@capture_err
@use_chat_lang()
async def start(self, ctx: Message, strings):
    if ctx.chat.type.value != "private":
        nama = ctx.from_user.mention if ctx.from_user else ctx.sender_chat.title
        try:
            return await ctx.reply_photo(
                photo=THUMB_PATH,
                caption=strings("start_msg").format(kamuh=nama, **EMOJI_FMT),
                reply_markup=keyboard,
            )
        except (ChatSendPhotosForbidden, ChatWriteForbidden):
            return await ctx.chat.leave()
    text_raw = (ctx.text or "").strip()
    if len(text_raw.split(None, 1)) > 1:
        name = text_raw.split(None, 1)[1].lower().strip()
        if "_" in name:
            module = name.split("_", 1)[1].strip()
            ordered = _helpable_keys_sorted()
            if module.isdigit() and 0 <= int(module) < len(ordered):
                module = ordered[int(module)]
            if module not in HELPABLE:
                await ctx.reply_msg(strings("pm_detail").format(**EMOJI_FMT), reply_markup=keyboard)
                return
            mod = HELPABLE[module]
            text = (
                strings("help_name").format(mod=mod.__MODULE__, **EMOJI_FMT)
                + (getattr(mod, "__HELP__", "") or "")
            )
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(strings("back_btn"), callback_data="help_back")]]
            )
            await ctx.reply_msg(
                text,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                message_effect_id=5104841245755180586,
            )
        elif name == "help":
            text, keyb = await help_parser(ctx.from_user.first_name)
            await ctx.reply_msg(
                text,
                reply_markup=keyb,
                parse_mode=ParseMode.HTML,
                message_effect_id=5104841245755180586,
            )
        else:
            await self.send_photo(
                ctx.chat.id,
                photo=THUMB_PATH,
                caption=home_text_pm,
                reply_markup=home_keyboard_pm,
                reply_to_message_id=ctx.id,
                message_effect_id=5104841245755180586,
            )
    else:
        await self.send_photo(
            ctx.chat.id,
            photo=THUMB_PATH,
            caption=home_text_pm,
            reply_markup=home_keyboard_pm,
            reply_to_message_id=ctx.id,
            message_effect_id=5104841245755180586,
        )


@app.on_callback_query(filters.regex("bot_commands"))
async def commands_callbacc(_, cb: CallbackQuery):
    text, keyb = await help_parser(cb.from_user.first_name)
    await app.send_message(
        cb.message.chat.id,
        text=text,
        reply_markup=keyb,
        parse_mode=ParseMode.HTML,
        message_effect_id=5104841245755180586,
    )
    await cb.message.delete_msg()


@app.on_callback_query(filters.regex("stats_callback"))
async def stats_callbacc(_, cb: CallbackQuery):
    text = await bot_sys_stats()
    await app.answer_callback_query(cb.id, text, show_alert=True)


@app.on_message(filters.command("help", COMMAND_HANDLER), group=-1)
@capture_err
@use_chat_lang()
async def help_command(_, ctx: Message, strings):
    if ctx.chat.type.value != "private":
        if len(ctx.command) >= 2:
            name = ((ctx.text or "").split(None, 1)[1] or "").replace(" ", "_").lower()
            if str(name) in HELPABLE:
                key = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text=strings("click_me").format(**EMOJI_FMT),
                                url=f"t.me/{BOT_USERNAME}?start=help_{name}",
                            )
                        ],
                    ]
                )
                await ctx.reply_msg(
                    strings("click_btn").format(nm=name, **EMOJI_FMT),
                    reply_markup=key,
                )
            else:
                await ctx.reply_msg(strings("pm_detail").format(**EMOJI_FMT), reply_markup=keyboard)
        else:
            await ctx.reply_msg(strings("pm_detail").format(**EMOJI_FMT), reply_markup=keyboard)
    elif len(ctx.command) >= 2:
        name = ((ctx.text or "").split(None, 1)[1] or "").replace(" ", "_").lower()
        if str(name) in HELPABLE:
            text = (
                strings("help_name").format(mod=HELPABLE[name].__MODULE__, **EMOJI_FMT)
                + HELPABLE[name].__HELP__
            )
            await ctx.reply_msg(
                text,
                disable_web_page_preview=True,
                message_effect_id=5104841245755180586,
            )
        else:
            text, help_keyboard = await help_parser(ctx.from_user.first_name)
            await ctx.reply_msg(
                text,
                reply_markup=help_keyboard,
                disable_web_page_preview=True,
                parse_mode=ParseMode.HTML,
                message_effect_id=5104841245755180586,
            )
    else:
        text, help_keyboard = await help_parser(ctx.from_user.first_name)
        await ctx.reply_msg(
            text,
            reply_markup=help_keyboard,
            disable_web_page_preview=True,
            parse_mode=ParseMode.HTML,
            message_effect_id=5104841245755180586,
        )


async def help_parser(name, keyb=None):
    if not keyb:
        keyb = InlineKeyboardMarkup(paginate_modules(0, HELPABLE, "help"))
    return (
        """<b>Xin chào {first_name}, tôi là {bot_name}{E_VIP}. Tôi là một bot với một số tính năng hữu ích.</b>

Bạn có thể chọn một tùy chọn bên dưới bằng cách nhấp vào nút.

Gửi lệnh /privacy nếu bạn muốn biết dữ liệu nào được bot thu thập.

Nếu bạn muốn tặng cà phê cho chủ sở hữu của tôi, bạn có thể gửi lệnh /donate để biết thêm thông tin.

<b>Tôi chỉ hỗ trợ Tiếng Việt {E_VN}</b>
""".format(
            E_VIP=E_VIP,
            E_VN=E_VN,
            first_name=name,
            bot_name="DoraSuper",
        ),
        keyb,
    )


@app.on_callback_query(filters.regex(r"help_(.*?)"))
@use_chat_lang()
async def help_button(self: Client, query: CallbackQuery, strings):
    home_match = re.match(r"help_home\((.+?)\)", query.data)
    mod_match = re.match(r"help_module\((.+?)\)", query.data)
    prev_match = re.match(r"help_prev\((.+?)\)", query.data)
    next_match = re.match(r"help_next\((.+?)\)", query.data)
    back_match = re.match(r"help_back", query.data)
    create_match = re.match(r"help_create", query.data)
    top_text = strings("help_txt").format(
        kamuh=query.from_user.first_name, bot=self.me.first_name, **EMOJI_FMT
    )
    if mod_match:
        raw = (mod_match[1] or "").strip()
        try:
            idx = int(raw.split(",")[-1].strip()) if "," in raw else int(raw)
        except (ValueError, IndexError):
            idx = 0
        ordered = _helpable_keys_sorted()
        if 0 <= idx < len(ordered):
            module_key = ordered[idx]
            mod = HELPABLE[module_key]
            text = (
                strings("help_name").format(mod=mod.__MODULE__, **EMOJI_FMT)
                + (getattr(mod, "__HELP__", "") or "")
            )
            await query.message.edit_msg(
                text=text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton(strings("back_btn"), callback_data="help_back")]]
                ),
                disable_web_page_preview=True,
            )
        else:
            await query.message.edit_msg(
                text=top_text,
                reply_markup=InlineKeyboardMarkup(paginate_modules(0, HELPABLE, "help")),
                disable_web_page_preview=True,
            )
    elif home_match:
        await app.send_msg(
            query.from_user.id,
            text=home_text_pm,
            reply_markup=home_keyboard_pm,
        )
        await query.message.delete_msg()
    elif prev_match:
        curr_page = int(prev_match[1])
        await query.message.edit_msg(
            text=top_text,
            reply_markup=InlineKeyboardMarkup(
                paginate_modules(curr_page - 1, HELPABLE, "help")
            ),
            disable_web_page_preview=True,
        )

    elif next_match:
        next_page = int(next_match[1])
        await query.message.edit_msg(
            text=top_text,
            reply_markup=InlineKeyboardMarkup(
                paginate_modules(next_page + 1, HELPABLE, "help")
            ),
            disable_web_page_preview=True,
        )

    elif back_match:
        await query.message.edit_msg(
            text=top_text,
            reply_markup=InlineKeyboardMarkup(paginate_modules(0, HELPABLE, "help")),
            disable_web_page_preview=True,
        )

    elif create_match:
        text, keyb = await help_parser(query.from_user.first_name)
        await query.message.edit_msg(
            text=text,
            reply_markup=keyb,
            disable_web_page_preview=True,
            parse_mode=ParseMode.HTML,
        )

    try:
        await self.answer_callback_query(query.id)
    except Exception:
        pass