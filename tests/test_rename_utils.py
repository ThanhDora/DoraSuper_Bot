import importlib.util, pathlib

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
