"""Test packaging / path UI per Ask Fatture."""
import sys
from pathlib import Path

import desktop as desktop_launcher
from app.main import static_dir
from app.version import APP_VERSION


def test_app_version():
    assert APP_VERSION == "0.3.0"


def test_static_dir_points_to_repo():
    expected = Path(__file__).resolve().parents[1] / "app" / "static"
    assert static_dir() == expected
    assert (static_dir() / "index.html").is_file()


def test_desktop_headless_flag(monkeypatch):
    monkeypatch.delenv("ASK_FATTURE_HEADLESS", raising=False)
    monkeypatch.delenv("ASKFATTURE_HEADLESS", raising=False)
    assert desktop_launcher.headless_mode() is False
    monkeypatch.setenv("ASK_FATTURE_HEADLESS", "1")
    assert desktop_launcher.headless_mode() is True


def test_ensure_stdio_recovers_windowed_none_handles(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    desktop_launcher.ensure_stdio()
    assert sys.stdout is not None
    assert sys.stderr is not None
    assert hasattr(sys.stdout, "isatty")
    assert sys.stdout.isatty() is False
