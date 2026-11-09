import importlib.util, pathlib
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "rename_utils", pathlib.Path(__file__).parent.parent / "dorasuper/helper/rename_utils.py")
ru = importlib.util.module_from_spec(spec); spec.loader.exec_module(ru)


def test_prefix_suffix():
    assert ru.add_prefix_suffix("phim.mkv", "[Dora]", "1080p") == "[Dora] phim 1080p.mkv"
    assert ru.add_prefix_suffix("phim.mkv") == "phim.mkv"


def test_extension():
    assert ru.ensure_extension("moi", "cu.mp4") == "moi.mp4"
    assert ru.ensure_extension("moi", "noext") == "moi.mkv"
    assert ru.ensure_extension("a.zip", "b.mp4") == "a.zip"


def test_metadata_parse_and_cmd():
    m = ru.parse_metadata("--change-title T\n--change-video-title V\n--change-author A")
    assert m["title"] == "T" and m["video_title"] == "V" and m["author"] == "A"
    cmd = ru.build_ffmpeg_cmd("i", "o", m, [{"index": 0, "codec_type": "video"}, {"index": 1, "codec_type": "audio"}])
    assert "title=V" in cmd and "-metadata:s:0" in cmd and cmd[-1] == "o"


def test_caption():
    assert ru.format_caption("{filename} - {filesize}", "a.mp4", "1 MB", "00:00:01") == "a.mp4 - 1 MB"
    assert ru.safe_filename('a/b:c') == "a_b_c"


def test_artwork_url_larger():
    assert "512x512" in ru.artwork_url_larger("https://x/100x100bb.jpg")
    assert "512x512" in ru.artwork_url_larger("https://x/60x60bb.jpg")
    same = "https://x/512x512bb.jpg"
    assert ru.artwork_url_larger(same) == same
    assert ru.artwork_url_larger("") == ""
    assert ru.artwork_url_larger(None) is None



def test_extract_bundle_info_from_ipa(tmp_path):
    import zipfile, plistlib
    ipa = tmp_path / "demo.ipa"
    plist = {
        "CFBundleIdentifier": "com.example.demo",
        "CFBundleDisplayName": "DemoApp",
        "CFBundleShortVersionString": "1.2.3",
    }
    with zipfile.ZipFile(ipa, "w") as z:
        z.writestr("Payload/Demo.app/Info.plist", plistlib.dumps(plist))
    bid, name, ver = ru.extract_bundle_info_from_ipa(str(ipa))
    assert bid == "com.example.demo"
    assert name == "DemoApp"
    assert ver == "1.2.3"
    bid2, _, _ = ru.get_bundle_id_from_file(str(ipa), extension_hint="x.ipa")
    assert bid2 == "com.example.demo"



def test_caption_gamename():
    assert ru.format_caption("{gamename} - {filename}", "a.ipa", "1MB", "00:00:00", "My Game") == "My Game - a.ipa"


def test_sanitize_and_search_terms():
    assert "/" not in ru.sanitize_filename_for_app("A/B:C")
    terms = ru._search_terms_for_bundle("com.company.myapp")
    assert "com.company.myapp" in terms and "myapp" in terms


def test_no_ipa_artwork_inject():
    """Regression: không còn chèn iTunesArtwork vào nội dung IPA."""
    src = Path(__file__).parent.parent / "dorasuper/helper/rename_utils.py"
    plugin = Path(__file__).parent.parent / "dorasuper/plugins/file_rename.py"
    s = src.read_text(encoding="utf-8")
    p = plugin.read_text(encoding="utf-8")
    assert "inject_itunes_artwork_into_ipa" not in s
    assert "fetch_itunes_artwork_and_inject_ipa" not in s
    assert "create_itunes_artwork" not in s
    assert "fetch_itunes_artwork_and_inject_ipa" not in p
    assert "chèn vào IPA" not in p
    assert "fetch_itunes_artwork" in p  # thumb vẫn giữ
