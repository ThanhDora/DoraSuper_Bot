from tiensiteo import app
from tiensiteo.core.decorator.errors import capture_err
from tiensiteo.vars import COMMAND_HANDLER

from pyrogram import filters
from pyrogram.types import Message

import aiohttp
import io
import matplotlib.pyplot as plt
import numpy as np
import datetime
from typing import List, Tuple, Optional, Dict

API_BASE = "https://api.dabeecao.org/goldprice"

# -----------------------------
# Helpers
# -----------------------------
async def fetch_json(url: str, timeout: int = 15) -> Optional[dict]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=timeout) as r:
                if r.status == 200:
                    return await r.json()
    except Exception:
        return None
    return None


def compact_money(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        return "-"
    if v >= 1_000_000_000:
        val = v / 1_000_000_000
        s = f"{val:.1f}".rstrip('0').rstrip('.')
        return f"{s} tỷ"
    if v >= 1_000_000:
        val = v / 1_000_000
        if abs(val - round(val)) < 0.01:
            return f"{int(round(val))} triệu"
        return f"{val:.1f}".rstrip('0').rstrip('.') + " triệu"
    if v >= 1_000:
        val = v / 1_000
        if abs(val - round(val)) < 0.01:
            return f"{int(round(val))} nghìn"
        return f"{val:.0f} nghìn"
    return f"{int(v)} đ"


def readable_money(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        return "0 đ"
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f} tỷ"
    if v >= 1_000_000:
        val = v / 1_000_000
        if abs(val - round(val)) < 0.01:
            return f"{int(round(val))} triệu"
        return f"{val:.1f} triệu"
    if v >= 1_000:
        return f"{v/1_000:.0f} nghìn"
    return f"{int(v)} đ"


def trend_icon(t: str) -> str:
    return "📈" if t == "increased" else "📉" if t == "decreased" else "⏺️"


def readable_name(code: str) -> str:
    code = code.lower().replace(" ", "").replace("_", "")
    if "nhan" in code:
        return "Nhẫn trơn vàng 1 chỉ (9999)"
    if "nutrang" in code:
        pct = ''.join([c for c in code if c.isdigit()])
        return f"Vàng nữ trang {pct}"
    mapping = {
        "1c": "Vàng miếng SJC 1 chỉ",
        "5c": "Vàng miếng SJC 5 chỉ",
        "1l": "Vàng miếng SJC 1 lượng (10 chỉ)",
        "sjc": "Vàng miếng SJC chuẩn 1 lượng",
        "9999": "Vàng 9999 (24K)",
    }
    return mapping.get(code, f"Vàng {code.upper()}")


def short_name(api_code: str) -> str:
    api_code = api_code.lower()
    mapping = {
        "1c": "SJC 1c",
        "5c": "SJC 5c",
        "1l": "SJC 1L",
        "nhan1c": "Nhẫn 1c",
        "nutrang_75": "NT 75",
        "nutrang_99": "NT 99",
        "nutrang_9999": "NT 9999",
    }
    return mapping.get(api_code, api_code.upper())


def get_price_from_prices(prices: Dict, key_primary: str) -> float:
    if not prices:
        return 0.0
    val = prices.get(key_primary)
    if val is None:
        return 0.0
    try:
        return float(val)
    except Exception:
        return 0.0


def parse_api_time(value: str, fmt_in: str = "%Y-%m-%d %H:%M:%S") -> str:
    if not value:
        return "N/A"
    try:
        dt = datetime.datetime.strptime(value, fmt_in)
        return dt.strftime("%H:%M:%S %d/%m/%Y")
    except Exception:
        return value


# -----------------------------
# Advice logic
# -----------------------------
def analyze_for_advice(history: List[dict]) -> Tuple[str, List[str]]:
    reasons = []
    if not history:
        return "CHỜ", ["Không có dữ liệu lịch sử để đưa ra gợi ý cụ thể."]

    entries = history[:5]
    prices = [get_price_from_prices(h.get("prices", {}), "buy_1l") for h in entries]
    prices = [p for p in prices if p > 0]
    if len(prices) < 2:
        return "CHỜ", ["Dữ liệu giá chưa đủ để phân tích xu hướng."]

    pct_changes = []
    for i in range(len(prices) - 1):
        newer = prices[i]
        older = prices[i + 1]
        if older == 0:
            continue
        pct = (newer - older) / older * 100.0
        pct_changes.append(pct)

    if not pct_changes:
        return "CHỜ", ["Dữ liệu không đủ để tính biến động."]

    avg_pct = sum(pct_changes) / len(pct_changes)
    avg_abs_pct = sum(abs(x) for x in pct_changes) / len(pct_changes)

    latest = entries[0]
    # New API uses avg_spread or buy_sell_diff in history
    spread = float(latest.get("buy_sell_diff", 0))

    if avg_pct > 0.3 and spread < 5_000_000:
        reasons.append(f"Giá trung bình tăng khoảng {avg_pct:.2f}% mỗi phiên.")
        reasons.append(f"Chênh lệch mua–bán trung bình hiện nhỏ ({compact_money(spread)}), thuận lợi để chốt lời.")
        return "BÁN", reasons

    if avg_pct < -0.3 and spread < 5_000_000:
        reasons.append(f"Giá trung bình giảm khoảng {abs(avg_pct):.2f}% mỗi phiên.")
        reasons.append(f"Chênh lệch mua–bán trung bình hiện nhỏ ({compact_money(spread)}), phù hợp để mua tích lũy.")
        return "MUA", reasons

    if avg_abs_pct > 1.5 or spread > 10_000_000:
        reasons.append("Biến động giá cao hoặc chênh lệch mua–bán trung bình lớn.")
        reasons.append("Khuyến nghị tránh giao dịch ngắn hạn, chờ ổn định.")
        return "TRÁNH GIAO DỊCH", reasons

    reasons.append("Không có tín hiệu đủ mạnh để khuyến nghị mua hoặc bán ngay.")
    return "CHỜ", reasons


# -----------------------------
# Create TradingView-style Card
# -----------------------------
def create_card_image(table_rows: List[List[str]], header_title: str = "GOLD MARKET OVERVIEW", updated_at: str = "") -> Optional[io.BytesIO]:
    buf = io.BytesIO()
    try:
        width = 900
        row_h = 60
        header_h = 150
        n_rows = len(table_rows)
        height = header_h + max(n_rows, 1) * row_h + 40

        fig = plt.figure(figsize=(width / 100, height / 100), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, width)
        ax.set_ylim(0, height)
        ax.axis('off')

        ax.add_patch(plt.Rectangle((10, 10), width - 20, height - 20, fc='white', ec='#d6d6d6', lw=1.2))

        ax.add_patch(plt.Rectangle((10, height - header_h - 10), width - 20, header_h, fc="#1f77b4"))
        ax.text(width / 2, height - header_h / 2 + 35, header_title, ha='center', va='center', fontsize=26, fontweight='bold', color='white')

        if updated_at:
            ax.text(width / 2, height - header_h + 55, f"Cập nhật: {updated_at}", ha='center', va='center', fontsize=14, color='white')
        ax.text(width / 2, height - header_h + 25, "Nguồn: DC SJC Gold Price API", ha='center', va='center', fontsize=10, color='white')

        x_label, x_buy, x_sell, x_chi = 70, 320, 520, 700
        ax.text(x_label, height - header_h - 30, "Loại", fontsize=12, fontweight='bold')
        ax.text(x_buy, height - header_h - 30, "Mua", fontsize=12, fontweight='bold')
        ax.text(x_sell, height - header_h - 30, "Bán", fontsize=12, fontweight='bold')
        ax.text(x_chi, height - header_h - 30, "1 chỉ", fontsize=12, fontweight='bold')

        base_y = height - header_h - 70
        for i, row in enumerate(table_rows):
            y = base_y - i * row_h
            ax.plot([30, width - 30], [y + row_h / 2 - 10, y + row_h / 2 - 10], color='#eeeeee', linewidth=1)
            label, buy_txt, sell_txt, chi_txt, _ = row
            ax.text(x_label, y, label, fontsize=14)
            ax.text(x_buy, y, buy_txt, fontsize=13, color='#0a62a6')
            ax.text(x_sell, y, sell_txt, fontsize=13, color='#d9534f')
            ax.text(x_chi, y, chi_txt, fontsize=13)

        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf
    except Exception:
        try:
            plt.close('all')
        except Exception:
            pass
        return None


# -----------------------------
# Main command routing
# -----------------------------
@capture_err
@app.on_message(filters.command(["giavang"], prefixes=COMMAND_HANDLER))
async def goldprice_cmd(_, message: Message):
    args = message.text.split(maxsplit=1)
    sub = args[1].lower() if len(args) > 1 else ""
    if "-lichsu" in sub:
        await history_view(message)
    elif "-bieudo" in sub:
        await chart_view(message)
    elif "-tuvan" in sub:
        await advice_view(message)
    else:
        await current_view(message)


# -----------------------------
# Current View
# -----------------------------
async def current_view(message: Message):
    wait = await message.reply_text("⏳ Đang tải dữ liệu giá vàng...")
    data = await fetch_json(f"{API_BASE}/sjc")
    if not data or "results" not in data:
        return await wait.edit_text("⚠️ Không thể lấy dữ liệu từ máy chủ.")

    d = data["results"][0]

    raw_time = d.get("datetime_human") or d.get("datetime") or ""
    if isinstance(raw_time, int) or (isinstance(raw_time, str) and raw_time.isdigit()):
        try:
            ts = int(raw_time)
            dt = datetime.datetime.fromtimestamp(ts)
            updated_at_vn = dt.strftime("%H:%M:%S %d/%m/%Y")
        except Exception:
            updated_at_vn = str(raw_time)
    else:
        updated_at_vn = parse_api_time(raw_time)

    # New API: use 'avg_spread' and 'market_trend'
    diff_avg = float(data.get("avg_spread", 0))
    trend_price = data.get("market_trend", "stable")

    main_buy = get_price_from_prices(d, "buy_1l")
    main_sell = get_price_from_prices(d, "sell_1l")

    # Get specific diff for main item if available
    main_buy_diff = d.get("buy_1l_diff", 0)
    main_sell_diff = d.get("sell_1l_diff", 0)

    summary = (
        f"🕒 <i>Cập nhật: <b>{updated_at_vn}</b></i>\n\n"
        f"{trend_icon(trend_price)} Thị trường hôm nay đang "
        + ("<b>tăng</b>" if trend_price == "increased"
           else "<b>giảm</b>" if trend_price == "decreased"
           else "<b>ổn định</b>")
    )

    spread_text = f"{compact_money(diff_avg)}"
    summary += f". Chênh lệch mua–bán trung bình khoảng {spread_text}/lượng."

    explanation = (
        "ℹ️ <b>Giải thích:</b>\n"
        "• <b>Giá mua</b>: giá cửa hàng thu mua từ khách.\n"
        "• <b>Giá bán</b>: giá cửa hàng bán ra cho khách.\n"
        "• Δ: Mức thay đổi so với phiên trước.\n\n"
    )

    text = f"📊 {summary}\n\n{explanation}"
    
    # Formatter for diff
    def fmt_diff(val):
        if val == 0: return ""
        sym = "+" if val > 0 else ""
        return f" ({sym}{compact_money(val)})"

    text += (
        f"<blockquote expandable>"
        f"📌 <b>Giá chuẩn SJC (1 lượng)</b>:\n"
        f"• Mua: <b>{main_buy:,.0f} đ</b>{fmt_diff(main_buy_diff)}\n"
        f"• Bán: <b>{main_sell:,.0f} đ</b>{fmt_diff(main_sell_diff)}\n\n"
    )

    table_rows = []
    # FILTER: Exclude new API keys like '_diff' and '_trend'
    keys = sorted([k for k in d.keys() if k.startswith("buy_") and not k.endswith("_diff") and not k.endswith("_trend")])
    
    for k in keys:
        name = k.replace("buy_", "")
        buy = get_price_from_prices(d, k)
        sell = get_price_from_prices(d, f"sell_{name}")
        
        # Get specific diffs
        buy_diff = d.get(f"buy_{name}_diff", 0)
        sell_diff = d.get(f"sell_{name}_diff", 0)

        if buy == 0 and sell == 0:
            continue
            
        per_chi_buy = buy / 10 if buy else 0
        per_chi_sell = sell / 10 if sell else 0
        diff = (sell - buy) if (buy and sell) else 0
        
        table_rows.append([
            short_name(name),
            compact_money(buy),
            compact_money(sell),
            compact_money(per_chi_buy),
            compact_money(diff)
        ])
        
        text += f"• <b>{readable_name(name)}</b>\n"
        text += f"  - Mua: {buy:,.0f}{fmt_diff(buy_diff)} → 1 chỉ: {per_chi_buy:,.0f}\n"
        text += f"  - Bán: {sell:,.0f}{fmt_diff(sell_diff)} → 1 chỉ: {per_chi_sell:,.0f}\n"
        text += f"  - Chênh lệch mua–bán: {diff:,.0f} đ\n\n"

    text += (
        f"</blockquote>"
        "📈 <b>Lệnh mở rộng:</b>\n"
        "• <code>/giavang -lichsu</code> – Lịch sử 5 lần cập nhật gần nhất\n"
        "• <code>/giavang -bieudo</code> – Biểu đồ giá vàng 1L & 1C\n"
        "• <code>/giavang -tuvan</code> – Gợi ý thời điểm mua/bán (tham khảo)\n"
    )

    await wait.edit_text(text, disable_web_page_preview=True)

    buf = create_card_image(table_rows, header_title="BẢNG GIÁ VÀNG SJC", updated_at=updated_at_vn)
    if buf:
        try:
            await message.reply_photo(buf, caption=f"Nguồn: DC SJC Gold Price API")
        except Exception:
            pass


# -----------------------------
# History View
# -----------------------------
async def history_view(message: Message, limit: int = 5):
    wait = await message.reply_text("📜 Đang tải lịch sử giá...")
    data = await fetch_json(f"{API_BASE}/history?limit={limit}")
    if not data or "history" not in data:
        return await wait.edit_text("⚠️ Không thể tải lịch sử từ máy chủ.")

    history = data["history"]
    text = "📈 <b>Lịch sử 5 lần cập nhật gần nhất</b>\n"
    text += "ℹ️ Hiển thị theo thời gian cập nhật gốc của API.\n\n"
    text += "<blockquote expandable>"

    for i, h in enumerate(history, start=1):
        raw_time = h.get("last_update") or h.get("saved_at") or ""
        formatted_time = parse_api_time(raw_time)
        trend = h.get("price_trend", "stable")
        
        # New API: spread is just a number, trends are in 'trends' dict
        diff = float(h.get("buy_sell_diff", 0))

        prices = h.get("prices", {})
        diffs = h.get("diffs", {})

        buy_1l = get_price_from_prices(prices, "buy_1l")
        sell_1l = get_price_from_prices(prices, "sell_1l")
        
        # Get specific diff for buy_1l from the diffs dict
        delta_buy = float(diffs.get("buy_1l", 0))

        text += f"\n<b>{i}. 🕒 {formatted_time}</b>\n"
        text += f"{trend_icon(trend)} Xu hướng chung: {('tăng' if trend == 'increased' else 'giảm' if trend == 'decreased' else 'ổn định')}\n"
        text += f"• Mua 1L: {buy_1l:,.0f} đ ({('+' if delta_buy > 0 else '')}{delta_buy:,.0f} đ)\n"
        text += f"• Bán 1L: {sell_1l:,.0f} đ\n"
        text += f"• Chênh lệch mua–bán: {diff:,.0f} đ\n"

    text += "</blockquote>"
    await wait.edit_text(text, disable_web_page_preview=True)


# -----------------------------
# Chart View
# -----------------------------
async def chart_view(message: Message, limit: int = 10):
    wait = await message.reply_text("📈 Đang tạo biểu đồ...")

    data = await fetch_json(f"{API_BASE}/history?limit={limit}")
    if not data or "history" not in data:
        return await wait.edit_text("⚠️ Không thể tải dữ liệu biểu đồ.")

    hist = list(reversed(data["history"]))

    times = []
    buy_1l = []
    sell_1l = []
    spread = []

    for h in hist:
        raw_time = h.get("last_update") or h.get("saved_at") or ""
        parsed = parse_api_time(raw_time)

        if isinstance(parsed, str) and " " in parsed:
            hhmmss, dmy = parsed.split(" ")
            hhmm = hhmmss[:5]
            ddmm = dmy[:5]
            label = f"{ddmm}\n{hhmm}"
            times.append(label)
        else:
            times.append(parsed)

        prices = h.get("prices", {})
        buy_1l.append(get_price_from_prices(prices, "buy_1l"))
        sell_1l.append(get_price_from_prices(prices, "sell_1l"))
        spread.append(float(h.get("buy_sell_diff", 0)))

    x = np.arange(len(times))
    buf = io.BytesIO()

    try:
        fig, ax1 = plt.subplots(figsize=(7, 4))

        ax1.plot(x, buy_1l, marker='o', lw=2, label="Mua 1L")
        ax1.plot(x, sell_1l, marker='o', lw=2, linestyle='--', label="Bán 1L")

        ax1.set_xticks(x)
        ax1.set_xticklabels(times, fontsize=8)

        ax1.set_xlabel("Thời gian")
        ax1.set_ylabel("Giá (đ)")
        ax1.grid(True, linestyle='--', alpha=0.25)
        ax1.legend(loc='upper left', fontsize=9)

        ax2 = ax1.twinx()
        ax2.bar(x, spread, alpha=0.25, label="Chênh lệch", width=0.45)
        ax2.set_ylabel("Chênh lệch (đ)")
        ax2.legend(loc='upper right', fontsize=9)

        plt.title("Diễn biến giá vàng SJC (1L)")
        plt.subplots_adjust(bottom=0.20)

        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close(fig)

    except Exception as e:
        print("chart_view error:", e)
        buf = None

    last = hist[-1].get("price_trend") if hist else "stable"
    caption = (
        "📈 Xu hướng: <b>Tăng</b>" if last == "increased" else
        "📉 Xu hướng: <b>Giảm</b>" if last == "decreased" else
        "⏺️ Xu hướng: <b>Ổn định</b>"
    )

    if buf:
        await message.reply_photo(buf, caption=f"{caption}\nNguồn: DC SJC Gold Price API")
    else:
        await wait.edit_text("⚠️ Không thể tạo biểu đồ.")

    await wait.delete()

# -----------------------------
# Advice View
# -----------------------------
async def advice_view(message: Message, limit: int = 5):
    wait = await message.reply_text("🔎 Phân tích và đưa ra gợi ý...")
    data = await fetch_json(f"{API_BASE}/history?limit={limit}")
    if not data or "history" not in data:
        return await wait.edit_text("⚠️ Không thể lấy dữ liệu phân tích.")

    history = data["history"]
    decision, reasons = analyze_for_advice(history)

    intro = (
        "💡 <b>Gợi ý (tham khảo, dựa trên dữ liệu 3–5 phiên gần nhất)</b>\n"
        "Lưu ý: Đây là gợi ý tham khảo, không phải tư vấn đầu tư.\n\n"
    )

    advice_text = f"🔔 <b>KẾT LUẬN:</b> <b>{decision}</b>\n\n"
    advice_text += "<b>Những lý do chính:</b>\n"
    for r in reasons:
        advice_text += f"• {r}\n"

    advice_text += "\n<b>Hành động gợi ý:</b>\n"
    if decision == "BÁN":
        advice_text += "• Nếu bạn có lãi ngắn hạn, cân nhắc bán để chốt lời.\n"
    elif decision == "MUA":
        advice_text += "• Có thể mua tích lũy từng phần.\n"
    elif decision == "TRÁNH GIAO DỊCH":
        advice_text += "• Hạn chế giao dịch do biến động cao.\n"
    else:
        advice_text += "• Chờ thêm dữ liệu hoặc quan sát thêm.\n"

    await wait.edit_text(intro + advice_text, disable_web_page_preview=True)
