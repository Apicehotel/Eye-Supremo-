"""Icona prodotto Eye Supremo presente per packaging Windows."""
from pathlib import Path


def test_eye_supremo_icon_assets_exist():
    root = Path(__file__).resolve().parents[2]
    ico = root / "assets" / "icons" / "eye-supremo.ico"
    png = root / "assets" / "icons" / "eye-supremo-256.png"
    assert ico.exists() and ico.stat().st_size > 1000
    assert png.exists() and png.stat().st_size > 500
    # Header ICO / PNG
    assert ico.read_bytes()[:4] == b"\x00\x00\x01\x00"
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
