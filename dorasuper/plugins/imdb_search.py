import contextlib
import json
import re
import sys
import logging
from logging import getLogger

from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from pykeyboard import InlineButton, InlineKeyboard
from pyrogram import Client, enums
from pyrogram.errors import (
    ListenerTimeout,
    MediaCaptionTooLong,
    MediaEmpty,
    MessageIdInvalid,
    MessageNotModified,
    PhotoInvalidDimensions,
    WebpageCurlFailed,
    WebpageMediaEmpty,
)
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from database.imdb_db import add_imdbset, is_imdbset, remove_imdbset
from dorasuper import app
from dorasuper.helper import GENRES_EMOJI, Cache, fetch, get_random_string, search_jw
from dorasuper.emoji import E_CLOCK, E_CROSS, E_ERROR, E_FIRE, E_INFO, E_MEGAPHONE, E_MOVIE, E_NOTE, E_SEARCH, E_STAR, E_TROPHY, E_USER, E_WAIT, E_WARN
from utils import demoji

LIST_CARI = Cache(filename="imdb_cache.db", path="cache", in_memory=False)

LOGGER = getLogger("DoraSuper")

# IMDB Choose Language
@app.on_cmd("imdb")
async def imdb_choose(_, ctx: Message):
    if len(ctx.command) == 1:
        return await ctx.reply_msg(
            f"{E_INFO} Vui lòng thêm truy vấn sau CMD!\nVD: <code>/{ctx.command[0]} Jurassic World</code>",
            del_in=7,
        )
    if ctx.sender_chat:
        return await ctx.reply_msg(
            f"{E_WARN} Không thể xác định người dùng, vui lòng sử dụng trong cuộc trò chuyện riêng tư.", del_in=7
        )
    kuery = ctx.text.split(None, 1)[1]
    is_imdb, lang = await is_imdbset(ctx.from_user.id)
    if is_imdb:
        if lang == "eng":
            return await imdb_search_en(kuery, ctx)
        else:
            return await imdb_search_vi(kuery, ctx)
    buttons = InlineKeyboard()
    ranval = get_random_string(4)
    LIST_CARI.add(ranval, kuery, timeout=15)
    buttons.row(
        InlineButton("🇺🇸 English", f"imdbcari#eng#{ranval}#{ctx.from_user.id}"),
        InlineButton("Tiếng Việt", f"imdbcari#vie#{ranval}#{ctx.from_user.id}"),
    )
    buttons.row(InlineButton("🚩 Đặt ngôn ngữ mặc định", f"imdbset#{ctx.from_user.id}"))
    buttons.row(InlineButton(f"{E_CROSS} Đóng", f"close#{ctx.from_user.id}"))
    await ctx.reply_photo(
        "https://api.dabeecao.org/data/imdb.jpg",
        caption=f"{E_MOVIE} Xin chào {ctx.from_user.mention}, hãy chọn ngôn ngữ bạn muốn sử dụng của công cụ tìm kiếm IMDB. Nếu bạn muốn thiết lập ngôn ngữ mặc định cho mọi người dùng trong nhóm, hãy nhấp vào nút thứ ba.\n\n{E_CLOCK} Thời gian còn lại: 10 giây",
        reply_markup=buttons,
        quote=True,
    )


@app.on_cb("imdbset")
async def imdblangset(_, query: CallbackQuery):
    _, uid = query.data.split("#")
    if query.from_user.id != int(uid):
        return await query.answer("⚠️ Truy cập bị từ chối!", True)
    buttons = InlineKeyboard()
    buttons.row(
        InlineButton("🇺🇸 English", f"setimdb#eng#{query.from_user.id}"),
        InlineButton("Tiếng Việt", f"setimdb#vie#{query.from_user.id}"),
    )
    is_imdb, _ = await is_imdbset(query.from_user.id)
    if is_imdb:
        buttons.row(
            InlineButton("🗑 Xóa cài đặt người dùng", f"setimdb#rm#{query.from_user.id}")
        )
    buttons.row(InlineButton(f"{E_CROSS} Đóng", f"close#{query.from_user.id}"))
    with contextlib.suppress(MessageIdInvalid, MessageNotModified):
        await query.message.edit_caption(
            f"<i>{E_STAR} Vui lòng chọn ngôn ngữ có sẵn bên dưới..</i>", reply_markup=buttons
        )


@app.on_cb("setimdb")
async def imdbsetlang(_, query: CallbackQuery):
    _, lang, uid = query.data.split("#")
    if query.from_user.id != int(uid):
        return await query.answer(f"{E_WARN} Truy cập bị từ chối!", True)
    _, langset = await is_imdbset(query.from_user.id)
    if langset == lang:
        return await query.answer(f"{E_WARN} Thiết lập của bạn Đã là ({langset})!", True)
    with contextlib.suppress(MessageIdInvalid, MessageNotModified):
        if lang == "eng":
            await add_imdbset(query.from_user.id, lang)
            await query.message.edit_caption(
                f"{E_STAR} Language interface for IMDB has been changed to English."
            )
        elif lang == "vie":
            await add_imdbset(query.from_user.id, lang)
            await query.message.edit_caption(
                f"{E_STAR} Giao diện ngôn ngữ cho IMDB đã được thay đổi thành Tiếng Việt."
            )
        else:
            await remove_imdbset(query.from_user.id)
            await query.message.edit_caption(
                f"{E_STAR} Cài đặt người dùng cho IMDB đã bị xóa khỏi cơ sở dữ liệu."
            )


async def imdb_search_vi(kueri, message):
    BTN = []
    k = await message.reply_photo(
        "https://api.dabeecao.org/data/imdb.jpg",
        caption=f"{E_SEARCH} Duyệt qua <code>{kueri}</code> trong cơ sở dữ liệu IMDb...",
        quote=True,
    )
    msg = ""
    buttons = InlineKeyboard(row_width=4)
    with contextlib.redirect_stdout(sys.stderr):
        try:
            r = await fetch.get(
                f"https://v3.sg.media-imdb.com/suggestion/titles/x/{quote_plus(kueri)}.json"
            )
            r.raise_for_status()
            res = r.json().get("d")
            if not res:
                return await k.edit_caption(
                    f"{E_ERROR} Không tìm thấy kết quả nào cho truy vấn: <code>{kueri}</code>"
                )
            msg += (
                f"{E_STAR} Tìm thấy ({len(res)}) kết quả cho truy vấn: <code>{kueri}</code>\n\n"
            )
            for num, movie in enumerate(res, start=1):
                title = movie.get("l")
                if year := movie.get("yr"):
                    year = f"({year})"
                elif year := movie.get("y"):
                    year = f"({year})"
                else:
                    year = "(N/A)"
                typee = movie.get("q", "N/A").replace("feature", "movie").title()
                movieID = re.findall(r"tt(\d+)", movie.get("id"))[0]
                msg += f"{num}. {title} {year} - {typee}\n"
                BTN.append(
                    InlineKeyboardButton(
                        text=num,
                        callback_data=f"imdbres_vi#{message.from_user.id}#{movieID}",
                    )
                )
            BTN.extend(
                (
                    InlineKeyboardButton(
                        text=f"🚩 Ngôn ngữ",
                        callback_data=f"imdbset#{message.from_user.id}",
                    ),
                    InlineKeyboardButton(
                        text=f"{E_CROSS} Đóng",
                        callback_data=f"close#{message.from_user.id}",
                    ),
                )
            )
            buttons.add(*BTN)
            await k.edit_caption(msg, reply_markup=buttons)
        except httpx.HTTPError as exc:
            await k.edit_caption(f"{E_ERROR} Ngoại lệ HTTP cho tìm kiếm IMDB - <code>{exc}</code>")
        except (MessageIdInvalid, MessageNotModified):
            pass
        except Exception as err:
            await k.edit_caption(
                f"{E_ERROR} Rất tiếc, không tải được danh sách tiêu đề trên IMDb. Có thể có giới hạn hoặc server lỗi.\n\n<b>ERROR:</b> <code>{err}</code>"
            )


async def imdb_search_en(kueri, message):
    BTN = []
    k = await message.reply_photo(
        "https://api.dabeecao.org/data/imdb.jpg",
        caption=f"{E_SEARCH} Searching <code>{kueri}</code> in IMDb Database...",
        quote=True,
    )
    msg = ""
    buttons = InlineKeyboard(row_width=4)
    with contextlib.redirect_stdout(sys.stderr):
        try:
            r = await fetch.get(
                f"https://v3.sg.media-imdb.com/suggestion/titles/x/{quote_plus(kueri)}.json"
            )
            r.raise_for_status()
            res = r.json().get("d")
            if not res:
                return await k.edit_caption(
                    f"{E_ERROR} Result not found for keywords: <code>{kueri}</code>"
                )
            msg += (
                f"{E_STAR} Found ({len(res)}) result for keywords: <code>{kueri}</code>\n\n"
            )
            for num, movie in enumerate(res, start=1):
                title = movie.get("l")
                if year := movie.get("yr"):
                    year = f"({year})"
                elif year := movie.get("y"):
                    year = f"({year})"
                else:
                    year = "(N/A)"
                typee = movie.get("q", "N/A").replace("feature", "movie").title()
                movieID = re.findall(r"tt(\d+)", movie.get("id"))[0]
                msg += f"{num}. {title} {year} - {typee}\n"
                BTN.append(
                    InlineKeyboardButton(
                        text=num,
                        callback_data=f"imdbres_en#{message.from_user.id}#{movieID}",
                    )
                )
            BTN.extend(
                (
                    InlineKeyboardButton(
                        text="🚩 Language",
                        callback_data=f"imdbset#{message.from_user.id}",
                    ),
                    InlineKeyboardButton(
                        text="❌ Close",
                        callback_data=f"close#{message.from_user.id}",
                    ),
                )
            )
            buttons.add(*BTN)
            await k.edit_caption(msg, reply_markup=buttons)
        except httpx.HTTPError as exc:
            await k.edit_caption(f"{E_ERROR} HTTP Exception for IMDB Search - <code>{exc}</code>")
        except (MessageIdInvalid, MessageNotModified):
            pass
        except Exception as err:
            await k.edit_caption(
                f"Failed when requesting movies title. Maybe got rate limit or down.\n\n<b>ERROR:</b> <code>{err}</code>"
            )


@app.on_cb("imdbcari")
async def imdbcari(_, query: CallbackQuery):
    BTN = []
    _, lang, msg, uid = query.data.split("#")
    if lang == "vie":
        if query.from_user.id != int(uid):
            return await query.answer(f"{E_WARN} Truy cập bị từ chối!", True)
        try:
            kueri = LIST_CARI.get(msg)
            del LIST_CARI[msg]
        except KeyError:
            return await query.message.edit_caption(f"{E_WARN} Truy vấn gọi đã hết hạn")
        with contextlib.suppress(MessageIdInvalid, MessageNotModified):
            await query.message.edit_caption(
                f"<i>{E_SEARCH} Hiện đang tìm kiếm Cơ sở dữ liệu IMDB..</i>"
            )
        msg = ""
        buttons = InlineKeyboard(row_width=4)
        with contextlib.redirect_stdout(sys.stderr):
            try:
                r = await fetch.get(
                    f"https://v3.sg.media-imdb.com/suggestion/titles/x/{quote_plus(kueri)}.json"
                )
                r.raise_for_status()
                res = r.json().get("d")
                if not res:
                    return await query.message.edit_caption(
                        f"{E_ERROR} Không tìm thấy kết quả nào cho truy vấn: <code>{kueri}</code>"
                    )
                msg += f"{E_MOVIE} Tìm thấy ({len(res)}) kết quả của: <code>{kueri}</code> ~ {query.from_user.mention}\n\n"
                for num, movie in enumerate(res, start=1):
                    title = movie.get("l")
                    if year := movie.get("yr"):
                        year = f"({year})"
                    elif year := movie.get("y"):
                        year = f"({year})"
                    else:
                        year = "(N/A)"
                    typee = movie.get("q", "N/A").replace("feature", "movie").title()
                    movieID = re.findall(r"tt(\d+)", movie.get("id"))[0]
                    msg += f"{num}. {title} {year} - {typee}\n"
                    BTN.append(
                        InlineKeyboardButton(
                            text=num, callback_data=f"imdbres_vi#{uid}#{movieID}"
                        )
                    )
                BTN.extend(
                    (
                        InlineKeyboardButton(
                            text="🚩 Ngôn ngữ", callback_data=f"imdbset#{uid}"
                        ),
                        InlineKeyboardButton(
                            text=f"{E_CROSS} Đóng", callback_data=f"close#{uid}"
                        ),
                    )
                )
                buttons.add(*BTN)
                await query.message.edit_caption(msg, reply_markup=buttons)
            except httpx.HTTPError as exc:
                await query.message.edit_caption(
                    f"{E_ERROR} HTTP Exception for IMDB Search - <code>{exc}</code>"
                )
            except (MessageIdInvalid, MessageNotModified):
                pass
            except Exception as err:
                await query.message.edit_caption(
                    f"{E_ERROR} Rất tiếc, không tải được danh sách tiêu đề trên IMDb. Có thể có giới hạn hoặc server lỗi.\n\n<b>ERROR:</b> <code>{err}</code>"
                )
    else:
        if query.from_user.id != int(uid):
            return await query.answer(f"{E_WARN} Access Denied!", True)
        try:
            kueri = LIST_CARI.get(msg)
            del LIST_CARI[msg]
        except KeyError:
            return await query.message.edit_caption(f"{E_WARN} Callback Query Expired!")
        await query.message.edit_caption(f"<i>{E_SEARCH} Looking in the IMDB Database..</i>")
        msg = ""
        buttons = InlineKeyboard(row_width=4)
        with contextlib.redirect_stdout(sys.stderr):
            try:
                r = await fetch.get(
                    f"https://v3.sg.media-imdb.com/suggestion/titles/x/{quote_plus(kueri)}.json"
                )
                r.raise_for_status()
                res = r.json().get("d")
                if not res:
                    return await query.message.edit_caption(
                        f"{E_ERROR} Result not found for keywords: <code>{kueri}</code>"
                    )
                msg += f"{E_MOVIE} Found ({len(res)}) result for keywords: <code>{kueri}</code> ~ {query.from_user.mention}\n\n"
                for num, movie in enumerate(res, start=1):
                    title = movie.get("l")
                    if year := movie.get("yr"):
                        year = f"({year})"
                    elif year := movie.get("y"):
                        year = f"({year})"
                    else:
                        year = "(N/A)"
                    typee = movie.get("q", "N/A").replace("feature", "movie").title()
                    movieID = re.findall(r"tt(\d+)", movie.get("id"))[0]
                    msg += f"{num}. {title} {year} - {typee}\n"
                    BTN.append(
                        InlineKeyboardButton(
                            text=num, callback_data=f"imdbres_en#{uid}#{movieID}"
                        )
                    )
                BTN.extend(
                    (
                        InlineKeyboardButton(
                            text="🚩 Language", callback_data=f"imdbset#{uid}"
                        ),
                        InlineKeyboardButton(
                            text=f"{E_CROSS} Close", callback_data=f"close#{uid}"
                        ),
                    )
                )
                buttons.add(*BTN)
                await query.message.edit_caption(msg, reply_markup=buttons)
            except httpx.HTTPError as exc:
                await query.message.edit_caption(
                    f"{E_ERROR} HTTP Exception for IMDB Search - <code>{exc}</code>"
                )
            except (MessageIdInvalid, MessageNotModified):
                pass
            except Exception as err:
                await query.message.edit_caption(
                    f"{E_ERROR} Failed when requesting movies title. Maybe got rate limit or down.\n\n<b>ERROR:</b> <code>{err}</code>"
                )


@app.on_cb("imdbres_vi")
async def imdb_id_callback(self: Client, query: CallbackQuery):
    i, userid, movie = query.data.split("#")
    if query.from_user.id != int(userid):
        return await query.answer("⚠️ Truy cập bị từ chối!", True)
    with contextlib.redirect_stdout(sys.stderr):
        try:
            await query.message.edit_caption(f"{E_WAIT} Yêu cầu của bạn đang được xử lý.. ")
            imdb_url = f"https://www.imdb.com/title/tt{movie}/"
            resp = await fetch.get(imdb_url)
            resp.raise_for_status()
            sop = BeautifulSoup(resp, "lxml")
            r_json = json.loads(
                sop.find("script", attrs={"type": "application/ld+json"}).contents[0]
            )
            ott = await search_jw(
                r_json.get("alternateName") or r_json.get("name"), "ID"
            )
            typee = r_json.get("@type", "")
            res_str = ""
            tahun = (
                re.findall(r"\d{4}\W\d{4}|\d{4}-?", sop.title.text)[0]
                if re.findall(r"\d{4}\W\d{4}|\d{4}-?", sop.title.text)
                else "N/A"
            )
            res_str += f"<b>{E_MOVIE} Tên phim:</b> <a href='{imdb_url}'>{r_json.get('name')} [{tahun}]</a> (<code>{typee}</code>)\n"
            if aka := r_json.get("alternateName"):
                res_str += f"<b>{E_MEGAPHONE} Tên khác:</b> <code>{aka}</code>\n\n"
            else:
                res_str += "\n"
            if durasi := sop.select('li[data-testid="title-techspec_runtime"]'):
                durasi = (
                    durasi[0]
                    .find(class_="ipc-metadata-list-item__content-container")
                    .text
                )
                res_str += f"<b>Thời lượng:</b> <code>{GoogleTranslator('auto', 'vi').translate(durasi)}</code>\n"
            if kategori := r_json.get("contentRating"):
                res_str += f"<b>Loại:</b> <code>{kategori}</code> \n"
            if rating := r_json.get("aggregateRating"):
                res_str += f"<b>Đánh giá:</b> <code>{rating['ratingValue']}⭐️ từ {rating['ratingCount']} người dùng</code>\n"
            if release := sop.select('li[data-testid="title-details-releasedate"]'):
                rilis = (
                    release[0]
                    .find(
                        class_="ipc-metadata-list-item__list-content-item ipc-metadata-list-item__list-content-item--link"
                    )
                    .text
                )
                rilis_url = release[0].find(
                    class_="ipc-metadata-list-item__list-content-item ipc-metadata-list-item__list-content-item--link"
                )["href"]
                res_str += f"<b>Ngày phát hành:</b> <a href='https://www.imdb.com{rilis_url}'>{rilis}</a>\n"
            if genre := r_json.get("genre"):
                genre = "".join(
                    f"{GENRES_EMOJI[i]} #{i.replace('-', '_').replace(' ', '_')}, "
                    if i in GENRES_EMOJI
                    else f"#{i.replace('-', '_').replace(' ', '_')}, "
                    for i in r_json["genre"]
                )
                res_str += f"<b>Thể loại:</b> {genre[:-2]}\n"
            if negara := sop.select('li[data-testid="title-details-origin"]'):
                country = "".join(
                    f"{demoji(country.text)} #{country.text.replace(' ', '_').replace('-', '_')}, "
                    for country in negara[0].findAll(
                        class_="ipc-metadata-list-item__list-content-item ipc-metadata-list-item__list-content-item--link"
                    )
                )
                res_str += f"<b>Quốc gia:</b> {country[:-2]}\n"
            if bahasa := sop.select('li[data-testid="title-details-languages"]'):
                language = "".join(
                    f"#{lang.text.replace(' ', '_').replace('-', '_')}, "
                    for lang in bahasa[0].findAll(
                        class_="ipc-metadata-list-item__list-content-item ipc-metadata-list-item__list-content-item--link"
                    )
                )
                res_str += f"<b>Ngôn ngữ:</b> {language[:-2]}\n"
            res_str += f"\n<b>{E_USER} Thông tin Cast:</b>\n"
            if directors := r_json.get("director"):
                director = "".join(
                    f"<a href='{i['url']}'>{i['name']}</a>, " for i in directors
                )
                res_str += f"<b>Đạo diễn:</b> {director[:-2]}\n"
            if creators := r_json.get("creator"):
                creator = "".join(
                    f"<a href='{i['url']}'>{i['name']}</a>, "
                    for i in creators
                    if i["@type"] == "Person"
                )
                res_str += f"<b>Kịch bản:</b> {creator[:-2]}\n"
            if actors := r_json.get("actor"):
                actor = "".join(
                    f"<a href='{i['url']}'>{i['name']}</a>, " for i in actors
                )
                res_str += f"<b>Các diễn viên tham gia:</b> {actor[:-2]}\n\n"
            if deskripsi := r_json.get("description"):
                summary = GoogleTranslator("auto", "vi").translate(deskripsi)
                res_str += f"<b>{E_NOTE} Nội dung chính:</b>\n<blockquote><code>{summary}</code></blockquote>\n\n"
            if keywd := r_json.get("keywords"):
                key_ = "".join(
                    f"#{i.replace(' ', '_').replace('-', '_')}, "
                    for i in keywd.split(",")
                )
                res_str += (
                    f"<b>{E_FIRE} Từ khóa:</b>\n<blockquote>{key_[:-2]}</blockquote>\n"
                )
            if award := sop.select('li[data-testid="award_information"]'):
                awards = (
                    award[0]
                    .find(class_="ipc-metadata-list-item__list-content-item")
                    .text
                )
                res_str += f"<b>{E_TROPHY} Giải thưởng:</b>\n<blockquote><code>{GoogleTranslator('auto', 'vi').translate(awards)}</code></blockquote>\n"
            else:
                res_str += "\n"
            if ott != "":
                res_str += f"Có sẵn tại:\n{ott}\n"
            res_str += f"<b>©️ IMDb by</b> @{self.me.username}"
            if trailer := r_json.get("trailer"):
                trailer_url = trailer["url"]
                markup = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Mở IMDB", url=imdb_url),
                            InlineKeyboardButton("Xem Trailer", url=trailer_url),
                        ]
                    ]
                )
            else:
                markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Mở IMDB", url=imdb_url)]]
                )
            if thumb := r_json.get("image"):
                try:
                    await query.message.edit_media(
                        InputMediaPhoto(
                            thumb, caption=res_str, parse_mode=enums.ParseMode.HTML
                        ),
                        reply_markup=markup,
                    )
                except (PhotoInvalidDimensions, WebpageMediaEmpty):
                    poster = thumb.replace(".jpg", "._V1_UX360.jpg")
                    await query.message.edit_media(
                        InputMediaPhoto(
                            poster, caption=res_str, parse_mode=enums.ParseMode.HTML
                        ),
                        reply_markup=markup,
                    )
                except (
                    MediaEmpty,
                    MediaCaptionTooLong,
                    WebpageCurlFailed,
                    MessageNotModified,
                ):
                    await query.message.reply(
                        res_str, parse_mode=enums.ParseMode.HTML, reply_markup=markup
                    )
                except Exception as err:
                    LOGGER.error(
                        f"Đã xảy ra lỗi khi hiển thị dữ liệu IMDB. ERROR: {err}"
                    )
            else:
                await query.message.edit_caption(
                    res_str, parse_mode=enums.ParseMode.HTML, reply_markup=markup
                )
        except httpx.HTTPError as exc:
            await query.message.edit_caption(
                f"{E_ERROR} Ngoại lệ HTTP cho tìm kiếm IMDB - <code>{exc}</code>"
            )
        except AttributeError:
            await query.message.edit_caption(
                f"{E_ERROR} Rất tiếc, không lấy được thông tin dữ liệu từ IMDB."
            )
        except (MessageNotModified, MessageIdInvalid):
            pass


@app.on_cb("imdbres_en")
async def imdb_en_callback(self: Client, query: CallbackQuery):
    i, userid, movie = query.data.split("#")
    if query.from_user.id != int(userid):
        return await query.answer(f"{E_WARN} Access Denied!", True)
    with contextlib.redirect_stdout(sys.stderr):
        try:
            await query.message.edit_caption(f"<i>{E_WAIT} Getting IMDb source..</i>")
            imdb_url = f"https://www.imdb.com/title/tt{movie}/"
            resp = await fetch.get(imdb_url)
            resp.raise_for_status()
            sop = BeautifulSoup(resp, "lxml")
            r_json = json.loads(
                sop.find("script", attrs={"type": "application/ld+json"}).contents[0]
            )
            ott = await search_jw(
                r_json.get("alternateName") or r_json.get("name"), "US"
            )
            typee = r_json.get("@type", "")
            res_str = ""
            tahun = (
                re.findall(r"\d{4}\W\d{4}|\d{4}-?", sop.title.text)[0]
                if re.findall(r"\d{4}\W\d{4}|\d{4}-?", sop.title.text)
                else "N/A"
            )
            res_str += f"<b>{E_MOVIE} Judul:</b> <a href='{imdb_url}'>{r_json.get('name')} [{tahun}]</a> (<code>{typee}</code>)\n"
            if aka := r_json.get("alternateName"):
                res_str += f"<b>📢 AKA:</b> <code>{aka}</code>\n\n"
            else:
                res_str += "\n"
            if durasi := sop.select('li[data-testid="title-techspec_runtime"]'):
                durasi = (
                    durasi[0]
                    .find(class_="ipc-metadata-list-item__content-container")
                    .text
                )
                res_str += f"<b>Duration:</b> <code>{durasi}</code>\n"
            if kategori := r_json.get("contentRating"):
                res_str += f"<b>Category:</b> <code>{kategori}</code> \n"
            if rating := r_json.get("aggregateRating"):
                res_str += f"<b>Rating:</b> <code>{rating['ratingValue']}⭐️ from {rating['ratingCount']} users</code>\n"
            if release := sop.select('li[data-testid="title-details-releasedate"]'):
                rilis = (
                    release[0]
                    .find(
                        class_="ipc-metadata-list-item__list-content-item ipc-metadata-list-item__list-content-item--link"
                    )
                    .text
                )
                rilis_url = release[0].find(
                    class_="ipc-metadata-list-item__list-content-item ipc-metadata-list-item__list-content-item--link"
                )["href"]
                res_str += f"<b>Rilis:</b> <a href='https://www.imdb.com{rilis_url}'>{rilis}</a>\n"
            if genre := r_json.get("genre"):
                genre = "".join(
                    f"{GENRES_EMOJI[i]} #{i.replace('-', '_').replace(' ', '_')}, "
                    if i in GENRES_EMOJI
                    else f"#{i.replace('-', '_').replace(' ', '_')}, "
                    for i in r_json["genre"]
                )
                res_str += f"<b>Genre:</b> {genre[:-2]}\n"
            if negara := sop.select('li[data-testid="title-details-origin"]'):
                country = "".join(
                    f"{demoji(country.text)} #{country.text.replace(' ', '_').replace('-', '_')}, "
                    for country in negara[0].findAll(
                        class_="ipc-metadata-list-item__list-content-item ipc-metadata-list-item__list-content-item--link"
                    )
                )
                res_str += f"<b>Country:</b> {country[:-2]}\n"
            if bahasa := sop.select('li[data-testid="title-details-languages"]'):
                language = "".join(
                    f"#{lang.text.replace(' ', '_').replace('-', '_')}, "
                    for lang in bahasa[0].findAll(
                        class_="ipc-metadata-list-item__list-content-item ipc-metadata-list-item__list-content-item--link"
                    )
                )
                res_str += f"<b>Language:</b> {language[:-2]}\n"
            res_str += f"\n<b>{E_USER} Cast Info:</b>\n"
            if r_json.get("director"):
                director = "".join(
                    f"<a href='{i['url']}'>{i['name']}</a>, "
                    for i in r_json["director"]
                )
                res_str += f"<b>Director:</b> {director[:-2]}\n"
            if r_json.get("creator"):
                creator = "".join(
                    f"<a href='{i['url']}'>{i['name']}</a>, "
                    for i in r_json["creator"]
                    if i["@type"] == "Person"
                )
                res_str += f"<b>Writer:</b> {creator[:-2]}\n"
            if r_json.get("actor"):
                actors = actors = "".join(
                    f"<a href='{i['url']}'>{i['name']}</a>, " for i in r_json["actor"]
                )
                res_str += f"<b>Stars:</b> {actors[:-2]}\n\n"
            if description := r_json.get("description"):
                res_str += f"<b>{E_NOTE} Summary:</b>\n<blockquote><code>{description}</code></blockquote>\n\n"
            if r_json.get("keywords"):
                key_ = "".join(
                    f"#{i.replace(' ', '_').replace('-', '_')}, "
                    for i in r_json["keywords"].split(",")
                )
                res_str += (
                    f"<b>{E_FIRE} Keywords:</b>\n<blockquote>{key_[:-2]}</blockquote>\n"
                )
            if award := sop.select('li[data-testid="award_information"]'):
                awards = (
                    award[0]
                    .find(class_="ipc-metadata-list-item__list-content-item")
                    .text
                )
                res_str += f"<b>{E_TROPHY} Awards:</b>\n<blockquote><code>{awards}</code></blockquote>\n"
            else:
                res_str += "\n"
            if ott != "":
                res_str += f"Available On:\n{ott}\n"
            res_str += f"<b>©️ IMDb by</b> @{self.me.username}"
            if trailer := r_json.get("trailer"):
                trailer_url = trailer["url"]
                markup = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Open IMDB", url=imdb_url),
                            InlineKeyboardButton("Trailer", url=trailer_url),
                        ]
                    ]
                )
            else:
                markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Open IMDB", url=imdb_url)]]
                )
            if thumb := r_json.get("image"):
                try:
                    await query.message.edit_media(
                        InputMediaPhoto(
                            thumb, caption=res_str, parse_mode=enums.ParseMode.HTML
                        ),
                        reply_markup=markup,
                    )
                except (PhotoInvalidDimensions, WebpageMediaEmpty):
                    poster = thumb.replace(".jpg", "._V1_UX360.jpg")
                    await query.message.edit_media(
                        InputMediaPhoto(
                            poster, caption=res_str, parse_mode=enums.ParseMode.HTML
                        ),
                        reply_markup=markup,
                    )
                except (
                    MediaCaptionTooLong,
                    WebpageCurlFailed,
                    MediaEmpty,
                    MessageNotModified,
                ):
                    await query.message.reply(
                        res_str, parse_mode=enums.ParseMode.HTML, reply_markup=markup
                    )
                except Exception as err:
                    LOGGER.error(f"Error while displaying IMDB Data. ERROR: {err}")
            else:
                await query.message.edit_caption(
                    res_str, parse_mode=enums.ParseMode.HTML, reply_markup=markup
                )
        except httpx.HTTPError as exc:
            await query.message.edit_caption(
                f"{E_ERROR} HTTP Exception for IMDB Search - <code>{exc}</code>"
            )
        except AttributeError:
            await query.message.edit_caption(f"{E_ERROR} Sorry, failed getting data from IMDB.")
        except (MessageNotModified, MessageIdInvalid):
            pass
