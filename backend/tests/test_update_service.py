from app.update_service import _version, pick_installer_asset


def test_version_compare_handles_v_prefix_numbers():
    assert _version("v2.0.1") > _version("2.0.0")
    assert _version("2.0.0") == _version("v2.0.0")
    assert _version("") == (0,)


def test_pick_installer_prefers_setup_exe():
    assets = [
        {"name": "notes.txt", "browser_download_url": "https://example/notes"},
        {"name": "EyeSupremo.exe", "browser_download_url": "https://example/exe"},
        {"name": "EyeSupremo-Setup.exe", "browser_download_url": "https://example/setup"},
    ]
    picked = pick_installer_asset(assets)
    assert picked is not None
    assert picked["name"] == "EyeSupremo-Setup.exe"


def test_pick_installer_accepts_setup_without_hyphen_prefix():
    assets = [{"name": "EyeSupremoSetup.exe", "browser_download_url": "https://example/setup"}]
    picked = pick_installer_asset(assets)
    assert picked is not None
    assert picked["name"] == "EyeSupremoSetup.exe"


def test_latest_release_marks_update_when_newer(monkeypatch):
    from app import update_service

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            import json
            return json.dumps({
                "tag_name": "v2.0.1",
                "html_url": "https://github.com/Apicehotel/Eye-Supremo-/releases/tag/v2.0.1",
                "published_at": "2026-10-07T00:00:00Z",
                "assets": [{
                    "name": "EyeSupremo-Setup.exe",
                    "browser_download_url": "https://github.com/Apicehotel/Eye-Supremo-/releases/download/v2.0.1/EyeSupremo-Setup.exe",
                }],
            }).encode()

    monkeypatch.setattr(update_service, "CURRENT_VERSION", "2.0.0")
    monkeypatch.setattr(update_service, "urlopen", lambda *a, **k: FakeResp())
    release = update_service.latest_release()
    assert release["update_available"] is True
    assert release["installer_available"] is True
    assert release["latest_version"] == "2.0.1"
    assert release["download_url"].endswith("EyeSupremo-Setup.exe")


def test_check_endpoint(client, monkeypatch):
    payload = {
        "current_version": "2.0.0",
        "latest_version": "2.0.1",
        "update_available": True,
        "installer_available": True,
        "download_url": "https://example/EyeSupremo-Setup.exe",
        "asset_name": "EyeSupremo-Setup.exe",
        "release_url": "https://example/release",
        "published_at": None,
        "message": None,
    }
    monkeypatch.setattr("app.routers.updates_eye.latest_release", lambda: payload)
    response = client.get("/api/eye/updates/check")
    assert response.status_code == 200
    assert response.json()["update_available"] is True


def test_download_redirects_to_github(client, monkeypatch):
    payload = {
        "current_version": "2.0.0",
        "latest_version": "2.0.1",
        "update_available": True,
        "installer_available": True,
        "download_url": "https://example.test/EyeSupremo-Setup.exe",
        "asset_name": "EyeSupremo-Setup.exe",
        "release_url": "https://example.test/release",
        "published_at": None,
        "message": None,
    }
    monkeypatch.setattr("app.routers.updates_eye.latest_release", lambda: payload)
    response = client.get("/api/eye/updates/download", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "https://example.test/EyeSupremo-Setup.exe"
