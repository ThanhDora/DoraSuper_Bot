import importlib.util
import pathlib
from io import BytesIO

from PIL import Image

spec = importlib.util.spec_from_file_location(
    "channel_up",
    pathlib.Path(__file__).parent.parent / "dorasuper/helper/channel_up.py",
)
cu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cu)


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
        emojis={"trophy": '<tg-emoji emoji-id="1">🏆</tg-emoji>', "gift": '<tg-emoji emoji-id="2">🎁</tg-emoji>'},
    )
    assert overflow is None
    assert "Clash of Clans" in caption
    assert "16.0.1" in caption
    assert "Supercell" in caption
    assert "Clash.ipa" in caption
    assert "Vô hạn tiền" in caption
    assert "Bất tử" in caption
    assert '<tg-emoji emoji-id="1">' in caption
    assert '<tg-emoji emoji-id="2">' in caption
    assert "Mở trên App Store" in caption
    assert "&lt;" not in caption


def test_caption_escapes_html():
    caption, _ = cu.build_channel_caption(name="<script>", features=["a <b> c"])
    assert "<script>" not in caption
    assert "&lt;script&gt;" in caption
    assert "&lt;b&gt;" in caption


def test_caption_omits_missing_fields():
    caption, _ = cu.build_channel_caption(name="Game")
    assert "Phiên bản" not in caption
    assert "Nhà phát hành" not in caption
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


def test_caption_keeps_all_features_despite_long_html():
    tag = '<tg-emoji emoji-id="5226431245918942763">x</tg-emoji>'
    emojis = {
        "trophy": tag, "sparkle": tag, "star": tag, "ios": tag,
        "user": tag, "link": tag, "gear": tag, "gift": tag, "shield": tag,
    }
    features = [f"Chức năng chi tiết số {i}" for i in range(15)]
    long_url = "https://apps.apple.com/vn/app/" + ("very-long-name-" * 12) + "/id529479190"
    caption, overflow = cu.build_channel_caption(
        name="Game Name",
        version="1.2.3",
        seller="Some Publisher",
        store_url=long_url,
        features=features,
        filename="VeryLongFileNameOfThePackage.ipa",
        emojis=emojis,
    )
    assert overflow is None
    for item in features:
        assert item in caption
    assert "VeryLongFileNameOfThePackage.ipa" in caption
    assert len(caption) > 1024  # HTML dài vì thẻ emoji + URL, nhưng chữ hiện ra vẫn đủ chỗ
    assert cu.caption_visible_len(caption) <= 1024


def test_render_appstore_poster():
    buf = BytesIO()
    Image.new("RGB", (64, 64), (30, 80, 200)).save(buf, format="PNG")
    raw = cu.render_appstore_poster(buf.getvalue(), title="Test Game", size=256)
    img = Image.open(BytesIO(raw))
    assert img.size == (256, 256)
    assert img.format == "JPEG"
