import importlib.util
import pathlib
import re
from io import BytesIO

from PIL import Image

spec = importlib.util.spec_from_file_location(
    "channel_up",
    pathlib.Path(__file__).parent.parent / "dorasuper/helper/channel_up.py",
)
cu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cu)

# Typical emoji / pictograph ranges that must not appear in channel captions.
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
        store_url="https://apps.apple.com/app/id529479190",
        features=["Vô hạn tiền", "Bất tử"],
        filename="Clash.ipa",
    )
    assert overflow is None
    assert "<b>Clash of Clans</b>" in caption
    assert "iOS · <code>16.0.1</code>" in caption
    assert "Người bán: Supercell" in caption
    assert "Clash.ipa" in caption
    assert "• Vô hạn tiền" in caption
    assert "• Bất tử" in caption
    assert "<b>Chức năng</b>" in caption
    assert "App Store" in caption
    assert "tg-emoji" not in caption
    assert "Mở trên App Store" not in caption
    assert _EMOJI_RE.search(caption) is None
    assert "&lt;" not in caption


def test_caption_escapes_html():
    caption, _ = cu.build_channel_caption(name="<script>", features=["a <b> c"])
    assert "<script>" not in caption
    assert "&lt;script&gt;" in caption
    assert "&lt;b&gt;" in caption


def test_caption_omits_missing_fields():
    caption, _ = cu.build_channel_caption(name="Game")
    assert "iOS" not in caption
    assert "Người bán" not in caption
    assert "Chức năng" not in caption
    assert "App Store" not in caption


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
        store_url=long_url,
        features=features,
        filename="VeryLongFileNameOfThePackage.ipa",
        emojis={"trophy": '<tg-emoji emoji-id="1">🏆</tg-emoji>'},  # ignored
    )
    assert overflow is None
    for item in features:
        assert item in caption
        assert f"• {item}" in caption
    assert "VeryLongFileNameOfThePackage.ipa" in caption
    assert "tg-emoji" not in caption
    assert _EMOJI_RE.search(caption) is None
    assert cu.caption_visible_len(caption) <= 1024
    # Trim order: with enough room filename and seller stay
    assert "Người bán: Some Publisher" in caption


def test_caption_trim_drops_filename_then_seller():
    # Force trim by tiny max_len relative to content, but leave room for features.
    features = ["Tính năng A", "Tính năng B"]
    caption, overflow = cu.build_channel_caption(
        name="Game",
        version="1.0",
        seller="SellerNameVeryLongXXXXXXXX",
        store_url="https://apps.apple.com/app/id1",
        features=features,
        filename="SuperLongPackageFileNameThatTakesSpace.ipa",
        max_len=120,
    )
    assert overflow is None
    for item in features:
        assert item in caption
    assert cu.caption_visible_len(caption) <= 120
    # With max_len=120, filename and possibly seller may be dropped first.
    assert "SuperLongPackageFileNameThatTakesSpace.ipa" not in caption


def test_render_appstore_poster():
    buf = BytesIO()
    Image.new("RGB", (64, 64), (30, 80, 200)).save(buf, format="PNG")
    raw = cu.render_appstore_poster(buf.getvalue(), title="Test Game", size=256)
    img = Image.open(BytesIO(raw))
    assert img.size == (256, 256)
    assert img.format == "JPEG"
