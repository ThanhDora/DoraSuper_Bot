"""Offline tests for itunes_utils (shared by /up)."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "itunes_utils", ROOT / "dorasuper/helper/itunes_utils.py"
)
iu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iu)


def test_artwork_url_larger():
    assert "512x512" in iu.artwork_url_larger("https://x/100x100bb.jpg")
    assert iu.artwork_url_larger("https://x/512x512bb.jpg") == "https://x/512x512bb.jpg"
    assert iu.artwork_url_larger("") == ""
    assert iu.artwork_url_larger(None) is None


def test_assets_and_best_art():
    assets = iu._assets_from_app({
        "trackName": "Demo",
        "artworkUrl512": "https://a/512.jpg",
        "artworkUrl100": "https://a/100.jpg",
        "version": "1.0",
    })
    assert assets["track_name"] == "Demo"
    assert iu._best_art_url(assets) == "https://a/512.jpg"
    assert iu._best_art_url({}) == ""


def test_rename_feature_removed():
    root = ROOT
    assert not (root / "dorasuper/plugins/file_rename.py").exists()
    assert not (root / "dorasuper/helper/rename_utils.py").exists()
    assert not (root / "database/rename_db.py").exists()
    # /up still points at itunes_utils
    cu = (root / "dorasuper/helper/channel_up.py").read_text(encoding="utf-8")
    assert "itunes_utils" in cu
    assert "rename_utils" not in cu
