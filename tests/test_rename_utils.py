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


def test_create_itunes_artwork():
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (64, 64), (20, 40, 200)).save(buf, format="PNG")
    raw = ru.create_itunes_artwork(buf.getvalue(), size=128)
    img = Image.open(BytesIO(raw))
    assert img.size == (128, 128)
    assert img.format == "PNG"


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


def test_inject_itunes_artwork(tmp_path):
    import zipfile
    ipa = tmp_path / "a.ipa"
    with zipfile.ZipFile(ipa, "w") as z:
        z.writestr("Payload/A.app/Info.plist", b"x")
        z.writestr("Payload/A.app/foo", b"bar")
    art = b"PNGDATA"
    out = ru.inject_itunes_artwork_into_ipa(str(ipa), art, out_dir=str(tmp_path))
    assert out and Path(out).exists()
    with zipfile.ZipFile(out) as z:
        assert "iTunesArtwork" in z.namelist()
        assert z.read("iTunesArtwork") == art
        assert z.read("Payload/A.app/foo") == b"bar"


def test_caption_gamename():
    assert ru.format_caption("{gamename} - {filename}", "a.ipa", "1MB", "00:00:00", "My Game") == "My Game - a.ipa"


def test_sanitize_and_search_terms():
    assert "/" not in ru.sanitize_filename_for_app("A/B:C")
    terms = ru._search_terms_for_bundle("com.company.myapp")
    assert "com.company.myapp" in terms and "myapp" in terms
