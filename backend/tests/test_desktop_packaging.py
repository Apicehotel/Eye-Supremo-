import sys
from pathlib import Path

from app.main import frontend_dist
import desktop as desktop_launcher


def test_frontend_dist_points_to_repo_build():
    expected = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    assert frontend_dist() == expected


def test_api_docs_available_alongside_optional_static(client):
    response = client.get("/api/docs")
    assert response.status_code == 200


def test_desktop_headless_flag(monkeypatch):
    monkeypatch.delenv("EYE_SUPREMO_HEADLESS", raising=False)
    monkeypatch.delenv("EYE_SUPREMO_NO_BROWSER", raising=False)
    assert desktop_launcher.headless_mode() is False
    monkeypatch.setenv("EYE_SUPREMO_HEADLESS", "1")
    assert desktop_launcher.headless_mode() is True
    monkeypatch.delenv("EYE_SUPREMO_HEADLESS", raising=False)
    monkeypatch.setenv("EYE_SUPREMO_NO_BROWSER", "1")
    assert desktop_launcher.headless_mode() is True


def test_ensure_stdio_recovers_windowed_none_handles(monkeypatch, tmp_path):
    """Simula PyInstaller --windowed: stdout/stderr None non devono far crashare uvicorn."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    desktop_launcher.ensure_stdio()
    assert sys.stdout is not None
    assert sys.stderr is not None
    assert hasattr(sys.stdout, "isatty")
    assert sys.stdout.isatty() is False


def test_desktop_launcher_never_imports_webbrowser():
    """L'exe deve restare una finestra app; nessun fallback a browser esterno."""
    source = Path(desktop_launcher.__file__).read_text(encoding="utf-8")
    assert "import webbrowser" not in source
    assert "webbrowser.open" not in source
    assert 'gui="edgechromium"' in source or "gui='edgechromium'" in source


def test_icon_asset_exists_for_packaging():
    icon = Path(__file__).resolve().parents[2] / "installer" / "assets" / "eye-supremo.ico"
    assert icon.is_file()
