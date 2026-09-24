from pathlib import Path
from unittest.mock import MagicMock, patch

from app.update_service import download_setup, is_newer
from app.version import APP_VERSION


def test_is_newer_semver():
    assert is_newer("1.3.2", "1.3.1")
    assert is_newer("v2.0.0", "1.9.9")
    assert not is_newer("1.3.1", "1.3.1")
    assert not is_newer("1.2.0", "1.3.1")


def test_updates_status_without_release(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.updates.fetch_latest_release",
        lambda: {
            "available": False,
            "update_available": False,
            "latest_version": None,
            "reason": "Nessuna release pubblicata su GitHub.",
        },
    )
    response = client.get("/api/updates/status")
    assert response.status_code == 200
    body = response.json()
    assert body["current_version"] == APP_VERSION
    assert body["auto_check"] is True
    assert body["available"] is False


def test_updates_settings_and_download(client, monkeypatch, tmp_path):
    monkeypatch.setenv("RANDFATTURE_DATA_DIR", str(tmp_path))
    saved = client.put("/api/updates/settings", json={"auto_check": True, "auto_install": True})
    assert saved.status_code == 200
    assert saved.json()["auto_install"] is True

    monkeypatch.setattr(
        "app.routers.updates.fetch_latest_release",
        lambda: {
            "available": True,
            "update_available": True,
            "latest_version": "9.9.9",
            "asset_url": "https://example.test/EyeSupremo-Setup.exe",
            "asset_name": "EyeSupremo-Setup.exe",
        },
    )

    def fake_download(url, name=None):
        target = tmp_path / "updates" / (name or "EyeSupremo-Setup.exe")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake-setup")
        return {"path": str(target), "filename": target.name, "sha256": "abc", "size": 10}

    monkeypatch.setattr("app.routers.updates.download_setup", fake_download)
    monkeypatch.setattr(
        "app.routers.updates.launch_installer",
        lambda path: {"launched": True, "path": str(path), "args": []},
    )
    response = client.post("/api/updates/download", json={"install": True})
    assert response.status_code == 200
    body = response.json()
    assert body["downloaded"] is True
    assert body["install"]["launched"] is True
    assert Path(body["path"]).exists()


def test_download_setup_streams_file(tmp_path, monkeypatch):
    monkeypatch.setenv("RANDFATTURE_DATA_DIR", str(tmp_path))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield b"abc"
            yield b"def"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.update_service.httpx.Client", FakeClient)
    result = download_setup("https://example.test/EyeSupremo-Setup.exe")
    assert Path(result["path"]).read_bytes() == b"abcdef"
    assert result["size"] == 6
