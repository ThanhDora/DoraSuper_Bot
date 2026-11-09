import importlib.util
import pathlib
import html as htmllib
import re
from io import BytesIO

from PIL import Image

spec = importlib.util.spec_from_file_location(
    "channel_up",
    pathlib.Path(__file__).parent.parent / "dorasuper/helper/channel_up.py",
)
cu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cu)

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U00002600-\U000026FF"
    "\U0000FE0F"
    "]"
)


def test_parse_appstore_track_id():
    assert cu.parse_appstore_track_id(
        "https://apps.apple.com/vn/app/clash-of-clans/id529479190"
    ) == "529479190"
    assert cu.parse_appstore_track_id("https://apps.apple.com/app/id529479190") == "529479190"
    assert cu.parse_appstore_track_id(
        "https://itunes.apple.com/us/app/clash-of-clans/id529479190?mt=8"
    ) == "529479190"
    assert cu.parse_appstore_track_id("https://example.com/game") is None
    assert cu.parse_appstore_track_id("") is None


def test_is_appstore_url():
    assert cu.is_appstore_url("https://apps.apple.com/us/app/x/id123456")
    assert not cu.is_appstore_url("https://google.com/id123456")
    assert not cu.is_appstore_url("xin chao")


def test_allowed_package():
    assert cu.is_allowed_package("Game.ipa")
    assert cu.is_allowed_package("game.DEB")
    assert cu.is_allowed_package("libhack.dylib")
    assert cu.is_allowed_package("bundle.tipa")
    assert cu.is_allowed_package("pack.zip")
    assert not cu.is_allowed_package("note.txt")
    assert not cu.is_allowed_package("photo.jpg")


def test_split_features():
    text = "- Vô hạn tiền\n• Bất tử\n\nMod menu\n"
    assert cu.split_features(text) == ["Vô hạn tiền", "Bất tử", "Mod menu"]


def test_feature_emoji_key():
    assert cu.feature_emoji_key("Vô hạn tiền") == "gift"
    assert cu.feature_emoji_key("Bất tử") == "shield"
    assert cu.feature_emoji_key("Mod menu") == "gear"
    assert cu.feature_emoji_key("Tăng tốc độ") == "rocket"
    assert cu.feature_emoji_key("Chơi vui") == "sparkle"


def test_build_channel_caption():
    caption, overflow = cu.build_channel_caption(
        name="Clash of Clans",
        version="16.0.1",
        seller="Supercell",
        bundle_id="com.supercell.magic",
        store_url="https://apps.apple.com/app/id529479190",
        features=["Vô hạn tiền", "Bất tử"],
        filename="Clash.ipa",
    )
    assert overflow is None
    assert "<b>Clash of Clans</b>" in caption
    assert "Phiên bản · <code>16.0.1</code>" in caption
    assert "Bundle · <code>com.supercell.magic</code>" in caption
    assert "Người bán" not in caption
    assert "Supercell" not in caption
    assert "Clash.ipa" not in caption
    assert "<blockquote><b>Chức năng</b>\n• Vô hạn tiền\n• Bất tử</blockquote>" in caption
    assert "App Store" in caption
    assert "tg-emoji" not in caption
    assert _EMOJI_RE.search(caption) is None
    assert "&lt;" not in caption


def test_caption_escapes_html():
    caption, _ = cu.build_channel_caption(name="<script>", features=["a <b> c & d"], bundle_id="com.<x>")
    assert "<script>" not in caption
    assert "&lt;script&gt;" in caption
    assert "&lt;b&gt;" in caption
    assert "com.&lt;x&gt;" in caption
    assert "<blockquote>" in caption


def test_caption_omits_missing_fields():
    caption, _ = cu.build_channel_caption(name="Game")
    assert "Phiên bản" not in caption
    assert "Bundle" not in caption
    assert "Người bán" not in caption
    assert "Chức năng" not in caption
    assert "App Store" not in caption
    assert "blockquote" not in caption


def test_caption_omits_seller_even_if_passed():
    caption, _ = cu.build_channel_caption(name="Game", seller="Someone", version="1.0")
    assert "Someone" not in caption
    assert "Người bán" not in caption
    assert "Bundle" not in caption


def test_caption_overflow():
    features = [f"Tính năng số {i} " + ("x" * 80) for i in range(30)]
    caption, overflow = cu.build_channel_caption(
        name="Game",
        features=features,
        max_len=400,
    )
    assert cu.caption_visible_len(caption) <= 400
    assert overflow


def test_caption_keeps_all_features_no_emoji():
    features = [
        "Vô hạn tiền vàng",
        "Bất tử / God mode",
        "Mod menu đầy đủ",
        "Tăng tốc độ x10",
        "Bypass anti-ban",
        "Aimbot headshot",
        "Hiện map radar",
        "Mở khóa VIP premium",
        "Hack cheat mod",
        "Skin nhân vật mới",
        "Chơi offline",
        "Auto farm tài nguyên",
    ]
    long_url = "https://apps.apple.com/vn/app/" + ("very-long-name-" * 12) + "/id529479190"
    caption, overflow = cu.build_channel_caption(
        name="Game Name",
        version="1.2.3",
        seller="Some Publisher",
        bundle_id="com.example.verylongbundlename.app",
        store_url=long_url,
        features=features,
        filename="VeryLongFileNameOfThePackage.ipa",
        emojis={"trophy": '<tg-emoji emoji-id="1">🏆</tg-emoji>'},
    )
    assert overflow is None
    for item in features:
        assert item in caption
        assert f"• {item}" in caption
    assert "VeryLongFileNameOfThePackage.ipa" not in caption
    assert "Some Publisher" not in caption
    assert "Bundle · <code>com.example.verylongbundlename.app</code>" in caption
    assert "<blockquote>" in caption and "</blockquote>" in caption
    assert "tg-emoji" not in caption
    assert _EMOJI_RE.search(caption) is None
    assert cu.caption_visible_len(caption) <= 1024


def test_caption_trim_drops_bundle_before_features():
    features = ["Tính năng A", "Tính năng B"]
    caption, overflow = cu.build_channel_caption(
        name="Game",
        version="1.0",
        seller="SellerIgnored",
        bundle_id="com.verylong.bundle.identifier.name.xxxxxxxx",
        store_url="https://apps.apple.com/app/id1",
        features=features,
        filename="SuperLongPackageFileNameThatTakesSpace.ipa",
        max_len=90,
    )
    assert overflow is None
    for item in features:
        assert item in caption
    assert cu.caption_visible_len(caption) <= 90
    assert "com.verylong.bundle.identifier.name.xxxxxxxx" not in caption
    assert "SellerIgnored" not in caption
    assert "<blockquote>" in caption



def test_caption_escapes_ampersand_features():
    """Regression: raw & in features must be &amp; so Telegram keeps <blockquote>."""
    features = [
        "Bất tử & Đầy năng lượng (HP/MP)",
        "Hồi chiêu kỹ năng (No Cooldown)",
        "Mở khóa 60 FPS & Hiển thị thông số trận đấu",
        "Tùy chỉnh tốc độ trận đấu (1.0x - 5.0x)",
        "Tùy chỉnh hệ số sát thương (1.0x - 10.0x)",
        "Bạo kích 100% & Xuyên giáp, kháng phép",
        "Né đòn tuyệt đối & Bách phát bách trúng",
        "Miễn nhiễm khống chế & Tự hóa giải Debuff",
        "Tăng tốc đánh & Tốc độ xuất chiêu (HAST x3)",
        "Hạ máu địch còn 1 HP & Phá lá chắn",
    ]
    caption, overflow = cu.build_channel_caption(
        name="Game",
        version="1.0.0",
        bundle_id="com.example.game",
        store_url="https://apps.apple.com/app/id1",
        features=features,
        filename="Game.ipa",
    )
    assert overflow is None
    assert "<blockquote>" in caption and "</blockquote>" in caption
    assert "<b>Chức năng</b>" in caption
    for item in features:
        assert htmllib.escape(item, quote=False) in caption
        assert f"• {htmllib.escape(item, quote=False)}" in caption
    # No raw & outside of HTML entities in the feature section
    body = caption
    # Remove legitimate entities / tags then ensure no bare &
    stripped = re.sub(r"&(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);", "", body)
    stripped = re.sub(r"<[^>]+>", "", stripped)
    assert "&" not in stripped
    assert "Bất tử &amp; Đầy năng lượng (HP/MP)" in caption
    visible = htmllib.unescape(re.sub(r"<[^>]+>", "", caption))
    assert "Bất tử & Đầy năng lượng (HP/MP)" in visible
    for item in features:
        assert item in visible
    assert cu.caption_visible_len(caption) <= 1024
    assert "Game.ipa" not in caption




def test_build_delivery_captions_full():
    features = [
        "Bất tử & Đầy năng lượng (HP/MP)",
        "Hồi chiêu kỹ năng (No Cooldown)",
        "Mod menu",
    ]
    caption, followup = cu.build_delivery_captions(
        name="Clash of Clans",
        version="16.0.1",
        bundle_id="com.supercell.magic",
        store_url="https://apps.apple.com/app/id529479190",
        features=features,
    )
    assert followup is None
    assert "<b>Clash of Clans</b>" in caption
    assert "Bundle · <code>com.supercell.magic</code>" in caption
    assert "<blockquote>" in caption
    assert "Bất tử &amp; Đầy năng lượng (HP/MP)" in caption
    assert "Người bán" not in caption
    assert ".ipa" not in caption
    for item in features:
        assert htmllib.escape(item, quote=False) in caption
    assert cu.caption_visible_len(caption) <= 1024


def test_build_delivery_captions_old_record_fallback():
    caption, followup = cu.build_delivery_captions(name="Old Game")
    assert followup is None
    assert caption == "<b>Old Game</b>"
    caption2, followup2 = cu.build_delivery_captions(name="")
    assert caption2 == "<b>File</b>"
    assert followup2 is None


def test_build_delivery_captions_overflow_followup():
    features = [f"Tính năng số {i} " + ("x" * 80) for i in range(40)]
    caption, followup = cu.build_delivery_captions(
        name="Game",
        version="1.0",
        bundle_id="com.example.app",
        store_url="https://apps.apple.com/app/id1",
        features=features,
        caption_max=400,
        text_max=4096,
    )
    assert followup is not None
    assert cu.caption_visible_len(caption) <= 400
    assert cu.caption_visible_len(followup) <= 4096
    assert "<blockquote>" in followup
    # Full follow-up should keep more features than the short caption.
    assert followup.count("•") >= caption.count("•")
    for item in features:
        assert htmllib.escape(item, quote=False) in followup


def test_normalize_stored_features():
    assert cu.normalize_stored_features(["A", " B ", "", None]) == ["A", "B"]
    assert cu.normalize_stored_features("- A\n• B\n") == ["A", "B"]
    assert cu.normalize_stored_features(None) == []



def test_membership_is_joined():
    assert cu.membership_is_joined("owner")
    assert cu.membership_is_joined("administrator")
    assert cu.membership_is_joined("member")
    assert cu.membership_is_joined("restricted", True)
    assert not cu.membership_is_joined("restricted", False)
    assert not cu.membership_is_joined("left")
    assert not cu.membership_is_joined("banned")
    assert cu.membership_is_banned("banned")
    assert cu.membership_is_banned("kicked")
    assert not cu.membership_is_banned("member")




def test_public_username_from_tme_url():
    assert cu.public_username_from_tme_url("https://t.me/dorateam") == "dorateam"
    assert cu.public_username_from_tme_url("https://t.me/DoraTeamMods") == "DoraTeamMods"
    assert cu.public_username_from_tme_url("https://telegram.me/Foo_Bar") == "Foo_Bar"
    assert cu.public_username_from_tme_url("https://t.me/+invite") is None
    assert cu.public_username_from_tme_url("https://t.me/joinchat/AbC") is None
    assert cu.public_username_from_tme_url("") is None
    assert cu.public_username_from_tme_url("https://example.com/x") is None


def test_evaluate_join_gate_decision_fail_closed():
    # no targets configured → allow
    d = cu.evaluate_join_gate_decision([], {})
    assert d["ok"] is True and d["checkable"] == 0
    # all joined → allow
    d = cu.evaluate_join_gate_decision(["channel", "group"], {"channel": "joined", "group": "joined"})
    assert d["ok"] is True and not d["missing"] and not d["errors"]
    # missing → block
    d = cu.evaluate_join_gate_decision(["channel"], {"channel": "missing"})
    assert d["ok"] is False and d["missing"] == ["channel"]
    # error / uncheckable → block (fail closed)
    d = cu.evaluate_join_gate_decision(["channel", "group"], {"channel": "error", "group": "joined"})
    assert d["ok"] is False and "channel" in d["errors"]
    # banned → block
    d = cu.evaluate_join_gate_decision(["group"], {"group": "banned"})
    assert d["ok"] is False and d["banned"] is True
    # left/kicked treated upstream as missing/banned; decision still fail-closed on missing
    d = cu.evaluate_join_gate_decision(["channel", "group"], {"channel": "missing", "group": "missing"})
    assert d["ok"] is False and set(d["missing"]) == {"channel", "group"}


def test_membership_left_kicked_not_joined():
    assert not cu.membership_is_joined("left")
    assert not cu.membership_is_joined("kicked")
    assert cu.membership_is_banned("kicked")
    assert cu.membership_is_banned("banned")

def test_should_autoban_on_leave():
    assert cu.should_autoban_on_leave(old_status="member", new_status="left")
    assert cu.should_autoban_on_leave(old_status="restricted", new_status="left")
    assert not cu.should_autoban_on_leave(old_status="member", new_status="banned")
    assert not cu.should_autoban_on_leave(
        old_status="member", new_status="left", left_by_admin=True,
    )
    assert not cu.should_autoban_on_leave(
        old_status="member", new_status="left", user_is_sudo=True,
    )
    assert not cu.should_autoban_on_leave(
        old_status="member", new_status="left", user_is_bot=True,
    )
    assert cu.should_clear_leave_ban_on_unban(old_status="banned", new_status="left")
    assert cu.should_clear_leave_ban_on_unban(old_status="banned", new_status="member")
    assert not cu.should_clear_leave_ban_on_unban(old_status="member", new_status="left")


def test_parse_promo_link_args():
    assert cu.parse_promo_link_args("")["action"] == "show"
    assert cu.parse_promo_link_args("off")["action"] == "clear"
    assert cu.parse_promo_link_args("here")["action"] == "here"
    p = cu.parse_promo_link_args("@MyChannel")
    assert p["action"] == "set" and p["url"] == "https://t.me/MyChannel"
    p2 = cu.parse_promo_link_args("https://t.me/+AbC -100123456")
    assert p2["action"] == "set"
    assert p2["url"] == "https://t.me/+AbC"
    assert p2["chat_id"] == -100123456
    p3 = cu.parse_promo_link_args("-100999")
    assert p3["action"] == "set" and p3["chat_id"] == -100999


def test_build_join_gate_keyboard_botapi():
    kb = cu.build_join_gate_keyboard_botapi(
        "deadbeef",
        channel_url="https://t.me/c",
        group_url="https://t.me/g",
    )
    rows = kb["inline_keyboard"]
    assert rows[0] == [
        {"text": "Kênh", "url": "https://t.me/c"},
        {"text": "Nhóm chat", "url": "https://t.me/g"},
    ]
    assert rows[1] == [{"text": "Đã tham gia, tải file", "callback_data": "upjoin_deadbeef"}]
    # no download URL that would bypass the gate
    assert all("upfile_" not in (b.get("url") or "") for row in rows for b in row)


def test_download_keyboard_botapi():
    kb = cu.build_download_keyboard_botapi("DoraSuper_Bot", "deadbeef")
    assert kb == {
        "inline_keyboard": [[
            {
                "text": "Tải file",
                "url": "https://t.me/DoraSuper_Bot?start=upfile_deadbeef",
            }
        ]]
    }
    assert cu.DOWNLOAD_BUTTON_TEXT == "Tải file"
    assert "<tg-emoji" not in kb["inline_keyboard"][0][0]["text"]
    assert len(kb["inline_keyboard"][0][0]["text"]) <= 64
    assert cu.build_upfile_url("@DoraSuper_Bot", "abc") == (
        "https://t.me/DoraSuper_Bot?start=upfile_abc"
    )


def test_download_keyboard_with_promo_links():
    kb = cu.build_download_keyboard_botapi(
        "DoraSuper_Bot",
        "tok",
        channel_url="https://t.me/MyChannel",
        group_url="https://t.me/+AbCdEf",
    )
    rows = kb["inline_keyboard"]
    assert len(rows) == 2
    assert rows[0] == [{"text": "Tải file", "url": "https://t.me/DoraSuper_Bot?start=upfile_tok"}]
    assert rows[1] == [
        {"text": "Kênh", "url": "https://t.me/MyChannel"},
        {"text": "Nhóm chat", "url": "https://t.me/+AbCdEf"},
    ]
    for btn in rows[0] + rows[1]:
        assert len(btn["text"]) <= 64
        assert "<tg-emoji" not in btn["text"]
    # Only channel
    kb2 = cu.build_download_keyboard_botapi(
        "Bot", "t", channel_url="https://t.me/c", group_url=None,
    )
    assert len(kb2["inline_keyboard"]) == 2
    assert kb2["inline_keyboard"][1] == [{"text": "Kênh", "url": "https://t.me/c"}]
    # Neither -> single row
    kb3 = cu.build_download_keyboard_botapi("Bot", "t")
    assert len(kb3["inline_keyboard"]) == 1


def test_normalize_telegram_link():
    assert cu.normalize_telegram_link("@MyChannel") == "https://t.me/MyChannel"
    assert cu.normalize_telegram_link("MyChannel") == "https://t.me/MyChannel"
    assert cu.normalize_telegram_link("https://t.me/MyChannel") == "https://t.me/MyChannel"
    assert cu.normalize_telegram_link("t.me/MyChannel") == "https://t.me/MyChannel"
    assert cu.normalize_telegram_link("http://t.me/MyChannel") == "https://t.me/MyChannel"
    assert cu.normalize_telegram_link("https://t.me/+InviteHash") == "https://t.me/+InviteHash"
    assert cu.normalize_telegram_link("https://t.me/joinchat/AAAA") == "https://t.me/joinchat/AAAA"
    assert cu.normalize_telegram_link("tg://resolve?domain=MyChannel") == "https://t.me/MyChannel"
    assert cu.normalize_telegram_link("https://example.com/x") is None
    assert cu.normalize_telegram_link("") is None
    assert cu.normalize_telegram_link("ab") is None  # too short username
    assert cu.is_clear_link_arg("off")
    assert cu.is_clear_link_arg("xóa")
    assert cu.is_clear_link_arg("XOA")
    assert not cu.is_clear_link_arg("@channel")


def test_reply_markup_to_botapi_from_dict():
    src = cu.build_download_keyboard_botapi("BotName", "tok123")
    assert cu.reply_markup_to_botapi(src) == src
    assert cu.reply_markup_to_botapi(None) is None


class _FakeBtn:
    def __init__(self, text, url=None, callback_data=None):
        self.text = text
        self.url = url
        self.callback_data = callback_data


class _FakeMarkup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def test_reply_markup_to_botapi_keeps_all_rows():
    src = cu.build_download_keyboard_botapi(
        "Bot", "tok",
        channel_url="https://t.me/c",
        group_url="https://t.me/g",
    )
    assert cu.reply_markup_to_botapi(src) == src
    assert len(src["inline_keyboard"]) == 2


def test_reply_markup_to_botapi_from_pyrogram_like():

    markup = _FakeMarkup([[_FakeBtn("Tải file", url="https://t.me/x?start=upfile_1")]])
    assert cu.reply_markup_to_botapi(markup) == {
        "inline_keyboard": [[{"text": "Tải file", "url": "https://t.me/x?start=upfile_1"}]]
    }


def test_render_appstore_poster():
    buf = BytesIO()
    Image.new("RGB", (64, 64), (30, 80, 200)).save(buf, format="PNG")
    raw = cu.render_appstore_poster(buf.getvalue(), title="Test Game", size=256)
    img = Image.open(BytesIO(raw))
    assert img.size == (256, 256)
    assert img.format == "JPEG"
