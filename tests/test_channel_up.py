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
    assert "<blockquote expandable><b>Chức năng</b>\n• Vô hạn tiền\n• Bất tử</blockquote>" in caption
    assert "App Store" in caption
    assert "tg-emoji" not in caption
    assert _EMOJI_RE.search(caption) is None
    assert "&lt;" not in caption




def test_features_use_expandable_blockquote():
    caption, _ = cu.build_channel_caption(name="Game", features=["Một", "Hai"])
    assert "<blockquote expandable>" in caption
    assert caption.count("<blockquote") == 1
    assert "</blockquote>" in caption
    # plain <blockquote> without expandable must not appear for features
    assert "<blockquote>" not in caption.replace("<blockquote expandable>", "")
    # visible len ignores expandable attribute / tags
    assert cu.caption_visible_len(caption) == cu.caption_visible_len(
        caption.replace("<blockquote expandable>", "").replace("</blockquote>", "")
    )


def test_html_strip_blockquote_expandable_attr():
    # mirrors plugin fallback regex
    import re
    sample = "<b>X</b>\n<blockquote expandable><b>Chức năng</b>\n• a &amp; b</blockquote>"
    stripped = re.sub(r"</?blockquote\b[^>]*>", "", sample, flags=re.I)
    assert "blockquote" not in stripped.lower()
    assert "Chức năng" in stripped
    assert cu.caption_visible_len(sample) < len(sample)


def test_caption_escapes_html():
    caption, _ = cu.build_channel_caption(name="<script>", features=["a <b> c & d"], bundle_id="com.<x>")
    assert "<script>" not in caption
    assert "&lt;script&gt;" in caption
    assert "&lt;b&gt;" in caption
    assert "com.&lt;x&gt;" in caption
    assert "<blockquote expandable>" in caption


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
    assert "<blockquote expandable>" in caption and "</blockquote>" in caption
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
    assert "<blockquote expandable>" in caption



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
    assert "<blockquote expandable>" in caption and "</blockquote>" in caption
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
    assert "<blockquote expandable>" in caption
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
    assert "<blockquote expandable>" in followup
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



def test_membership_check_result_never_joined_not_banned():
    assert cu.membership_check_result("left") == "missing"
    assert cu.membership_check_result("member") == "joined"
    assert cu.membership_check_result("banned") == "banned"
    assert cu.membership_check_result("kicked") == "banned"
    assert cu.membership_check_result("restricted", False) == "missing"
    assert cu.membership_check_result("restricted", True) == "joined"
    assert not cu.membership_is_banned("left")
    assert cu.membership_is_banned("banned")
    assert cu.membership_is_banned("kicked")


def test_join_gate_block_kind():
    assert cu.join_gate_block_kind(tg_banned=False, has_leave_ban_record=False) is None
    assert cu.join_gate_block_kind(tg_banned=False, has_leave_ban_record=True) is None
    assert cu.join_gate_block_kind(tg_banned=True, has_leave_ban_record=True) == "leave_ban"
    assert cu.join_gate_block_kind(tg_banned=True, has_leave_ban_record=False) == "admin_ban"


def test_evaluate_join_gate_left_is_missing_not_banned():
    d = cu.evaluate_join_gate_decision(
        ["channel", "group"],
        {"channel": "missing", "group": "missing"},
    )
    assert d["ok"] is False
    assert d["banned"] is False
    assert set(d["missing"]) == {"channel", "group"}


def test_should_autoban_on_leave():
    assert cu.should_autoban_on_leave(old_status="member", new_status="left", self_leave=True)
    assert cu.should_autoban_on_leave(
        old_status="restricted", new_status="left", self_leave=True, old_is_member=True,
    )
    assert not cu.should_autoban_on_leave(
        old_status="restricted", new_status="left", self_leave=True, old_is_member=False,
    )
    assert not cu.should_autoban_on_leave(old_status="member", new_status="banned", self_leave=True)
    assert not cu.should_autoban_on_leave(old_status="member", new_status="left")  # thiếu self_leave
    assert not cu.should_autoban_on_leave(
        old_status="member", new_status="left", self_leave=True, left_by_admin=True,
    )
    assert not cu.should_autoban_on_leave(
        old_status="member", new_status="left", self_leave=True, user_is_sudo=True,
    )
    assert not cu.should_autoban_on_leave(
        old_status="member", new_status="left", self_leave=True, user_is_bot=True,
    )
    assert not cu.should_autoban_on_leave(
        old_status="left", new_status="left", self_leave=True,
    )
    assert not cu.should_autoban_on_leave(
        old_status=None, new_status="left", self_leave=True,
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
    assert cu.DOWNLOAD_BUTTON_LABEL == "Tải file"
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


def test_parse_up_user_ref():
    assert cu.parse_up_user_ref("")["kind"] == "empty"
    assert cu.parse_up_user_ref("  ")["kind"] == "empty"
    assert cu.parse_up_user_ref("12345") == {"kind": "id", "value": 12345}
    assert cu.parse_up_user_ref("@Alice") == {"kind": "username", "value": "@Alice"}
    assert cu.parse_up_user_ref("Alice")["kind"] == "username"
    assert cu.parse_up_user_ref("!!!")["kind"] == "invalid"


def test_format_up_acl_entry_and_line():
    rec = {
        "_id": 42,
        "name": "Test <User>",
        "username": "tester",
        "decided_at": 1700000000,
        "status": "allowed",
    }
    info = cu.format_up_acl_entry(rec)
    assert info["user_id"] == 42
    assert info["username"] == "tester"
    assert "tg://user?id=42" in info["mention_html"]
    assert "&lt;User&gt;" in info["mention_html"]
    line = cu.render_up_acl_line(rec, "14:00 09/11/2026")
    assert "@tester" in line
    assert "<code>42</code>" in line
    assert "14:00 09/11/2026" in line


def test_channel_button_texts_are_plain():
    for label in (
        cu.DOWNLOAD_BUTTON_TEXT,
        cu.CHANNEL_BUTTON_TEXT,
        cu.GROUP_BUTTON_TEXT,
        cu.JOINED_BUTTON_TEXT,
        cu.APPROVE_BUTTON_TEXT,
        cu.REJECT_BUTTON_TEXT,
        cu.REVOKE_BUTTON_TEXT,
    ):
        assert "<tg-emoji" not in label
        assert "icon_custom_emoji" not in label
        assert len(label) <= 64
    assert cu.DOWNLOAD_BUTTON_TEXT == "Tải file"
    assert cu.CHANNEL_BUTTON_TEXT == "Kênh"
    assert cu.GROUP_BUTTON_TEXT == "Nhóm chat"
    assert cu.JOINED_BUTTON_TEXT == "Đã tham gia, tải file"
    assert cu.APPROVE_BUTTON_TEXT == "Duyệt"
    assert cu.REJECT_BUTTON_TEXT == "Từ chối"
    assert cu.REVOKE_BUTTON_TEXT == "Gỡ quyền"
    for label in (
        cu.DOWNLOAD_BUTTON_TEXT, cu.CHANNEL_BUTTON_TEXT, cu.GROUP_BUTTON_TEXT,
        cu.JOINED_BUTTON_TEXT, cu.APPROVE_BUTTON_TEXT, cu.REJECT_BUTTON_TEXT,
        cu.REVOKE_BUTTON_TEXT,
    ):
        assert not any(ch in label for ch in "📥📢💬✅❌")


def test_extract_http_url():
    assert cu.extract_http_url("https://apps.apple.com/app/id1") == "https://apps.apple.com/app/id1"
    assert cu.extract_http_url("xem https://example.com/game?x=1 nhé").startswith("https://example.com/game")
    assert cu.extract_http_url("www.example.com/mod") == "https://www.example.com/mod"
    assert cu.extract_http_url("xin chao") is None
    assert cu.extract_http_url("") is None
    assert cu.extract_http_url("https://testflight.apple.com/join/abc").startswith("https://testflight.apple.com/")


def test_is_skip_text():
    assert cu.is_skip_text("bỏ qua")
    assert cu.is_skip_text("  Bo Qua  ")
    assert cu.is_skip_text("-")
    assert cu.is_skip_text("skip")
    assert cu.is_skip_text("không")
    assert not cu.is_skip_text("1.2.3")
    assert not cu.is_skip_text("My Game")


def test_caption_link_label():
    assert cu.caption_link_label("https://apps.apple.com/app/id1") == "App Store"
    assert cu.caption_link_label("https://example.com/game") == "Link"
    assert cu.caption_link_label("https://example.com", "Link") == "Link"
    assert cu.caption_link_label("https://apps.apple.com/app/id1", "App Store") == "App Store"


def test_is_image_document():
    assert cu.is_image_document("image/jpeg", "x.bin")
    assert cu.is_image_document("application/octet-stream", "cover.PNG")
    assert not cu.is_image_document("application/zip", "game.ipa")
    assert not cu.is_image_document(None, None)


def test_caption_non_appstore_link_label():
    caption, _ = cu.build_channel_caption(
        name="Mod Game",
        version="1.0",
        store_url="https://example.com/mod",
        link_label="Link",
        features=["Mod menu"],
    )
    assert '>Link</a>' in caption
    assert "App Store" not in caption
    assert "https://example.com/mod" in caption
    assert "Phiên bản · <code>1.0</code>" in caption
    assert "Bundle" not in caption
    assert _EMOJI_RE.search(caption) is None


def test_caption_appstore_label_unchanged():
    caption, _ = cu.build_channel_caption(
        name="Clash of Clans",
        store_url="https://apps.apple.com/app/id529479190",
    )
    assert ">App Store</a>" in caption
    assert ">Link</a>" not in caption


def test_delivery_captions_respect_link_label():
    caption, followup = cu.build_delivery_captions(
        name="Game",
        version="2.0",
        store_url="https://testflight.apple.com/join/xyz",
        features=["Menu"],
        link_label="Link",
    )
    assert followup is None
    assert ">Link</a>" in caption
    assert "App Store" not in caption
    assert "Phiên bản · <code>2.0</code>" in caption


def test_render_poster_from_arbitrary_photo():
    buf = BytesIO()
    Image.new("RGB", (640, 360), (30, 80, 160)).save(buf, format="JPEG")
    poster = cu.render_appstore_poster(buf.getvalue(), title="Cover Game")
    img = Image.open(BytesIO(poster))
    assert img.format == "JPEG"
    assert img.size[0] == img.size[1]


class _User:
    def __init__(self, **kw):
        self.id = kw.get("id", 123)
        self.first_name = kw.get("first_name", "Nguyen")
        self.last_name = kw.get("last_name", "Van A")
        self.username = kw.get("username", "nguyenvana")
        self.language_code = kw.get("language_code", "vi")
        self.is_premium = kw.get("is_premium", True)
        self.is_bot = kw.get("is_bot", False)
        self.dc_id = kw.get("dc_id", 5)


def test_format_up_file_size():
    assert cu.format_up_file_size(None) == ""
    assert cu.format_up_file_size("x") == ""
    assert cu.format_up_file_size(512) == "512B"
    assert cu.format_up_file_size(1024) == "1.00 KB"
    assert cu.format_up_file_size(432537600).endswith("MB")


def test_channel_post_link():
    assert cu.channel_post_link(-100123, 99, "MyChan") == "https://t.me/MyChan/99"
    assert cu.channel_post_link(-1003476714676, 42) == "https://t.me/c/3476714676/42"
    assert cu.channel_post_link(None, None) is None


def test_download_log_delivered_no_emoji():
    rec = {
        "name": "Clash of Clans",
        "version": "16.0.1",
        "bundle_id": "com.supercell.clashofclans",
        "filename": "Clash.ipa",
        "file_size": 432537600,
        "post_url": "https://t.me/c/111/222",
    }
    text = cu.build_up_download_log(
        _User(), rec, delivered=True, when_str="14:00:00 10/11/2026 Asia/Saigon",
    )
    assert text.startswith("Tải file: đã gửi")
    assert "Thời gian: 14:00:00 10/11/2026 Asia/Saigon" in text
    assert "Tên: Nguyen Van A" in text
    assert "Username: @nguyenvana" in text
    assert 'href="tg://user?id=123"' in text
    assert "<code>123</code>" in text
    assert "Ngôn ngữ: vi" in text
    assert "Premium: có" in text
    assert "Bot: không" in text
    assert "DC: 5" in text
    assert "Tên: Clash of Clans" in text
    assert "Phiên bản: 16.0.1" in text
    assert "Bundle: <code>com.supercell.clashofclans</code>" in text
    assert 'href="https://t.me/c/111/222"' in text
    assert "Clash.ipa" in text
    assert _EMOJI_RE.search(text) is None


def test_download_log_blocked_and_optional_fields():
    user = _User(username=None, last_name="", language_code="", is_premium=False, dc_id=None)
    rec = {"name": "Mod Game", "filename": "mod.ipa"}
    text = cu.build_up_download_log(
        user, rec, delivered=False, block_reason="not_joined",
        when_str="14:01:00 10/11/2026 Asia/Saigon",
    )
    assert "Tải file: bị chặn — chưa tham gia Kênh/Nhóm chat" in text
    assert "Username: không có" in text
    assert "Premium: không" in text
    assert "DC: không rõ" in text
    assert "Bundle" not in text
    assert "Phiên bản" not in text
    assert "Bài đăng" not in text
    assert "mod.ipa" in text
    assert _EMOJI_RE.search(text) is None
    ban = cu.build_up_download_log(
        user, rec, delivered=False, block_reason="leave_ban", when_str="x",
    )
    assert "đã bị cấm vì rời" in ban
