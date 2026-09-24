from pathlib import Path

from app.main import frontend_dist


def test_frontend_dist_points_to_repo_build():
    expected = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    assert frontend_dist() == expected


def test_api_docs_available_alongside_optional_static(client):
    response = client.get("/api/docs")
    assert response.status_code == 200


def test_packaged_style_invoice_flow_when_ui_built(client):
    """Con frontend/dist presente (come nell'exe), UI statica e fatture coesistono."""
    dist = frontend_dist()
    if not dist.exists():
        return
    home = client.get("/")
    assert home.status_code == 200
    assert "text/html" in home.headers.get("content-type", "")
    fixture = Path(__file__).parent / "fixtures" / "fattura.xml"
    preview = client.post(
        "/api/imports/preview",
        files={"file": ("fattura.xml", fixture.read_bytes(), "application/xml")},
    ).json()
    assert preview["invoice"]["numero"] == "42/A"
    confirmed = client.post(f"/api/imports/{preview['job_id']}/confirm", json={})
    assert confirmed.status_code == 200
    detail = client.get(f"/api/invoices/{confirmed.json()['invoice_id']}").json()
    assert detail["numero"] == "42/A"
