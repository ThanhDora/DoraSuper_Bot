"""Offline checks for /donate support page link."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV = (ROOT / "dorasuper/plugins/dev.py").read_text(encoding="utf-8")

def test_donate_page_url_constant():
    assert 'DONATE_PAGE_URL = "https://thanhdora.github.io/"' in DEV

def test_donate_button_and_caption():
    assert 'InlineKeyboardButton("Ủng hộ", url=DONATE_PAGE_URL)' in DEV
    assert "https://thanhdora.github.io/" in DEV
    assert "Tính năng tắt" not in DEV.split("async def donate", 1)[1].split("async def ", 1)[0]

def test_bank_momo_kept():
    chunk = DEV.split("async def donate", 1)[1].split("async def ", 1)[0]
    assert "Vietcombank" in chunk and "DONATE_MOMO_URL" in chunk and "DONATE_PAYPAL_URL" in chunk
