import io
import zipfile
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "fattura.xml"


def test_eye_batch_import_accepts_multiple_files(client):
    content = FIXTURE.read_bytes()
    response = client.post(
        "/api/eye/invoices/import/preview-batch",
        files=[
            ("files", ("fattura-a.xml", content, "application/xml")),
            ("files", ("fattura-b.xml", content, "application/xml")),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] == 2
    assert payload["failed"] == 0
    assert payload["limit"] == 100
    assert all(item["ok"] for item in payload["items"])


def test_eye_batch_import_expands_zip_and_ignores_unsupported_files(client):
    content = FIXTURE.read_bytes()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("cartella/fattura-1.xml", content)
        zf.writestr("../fattura-2.xml", content)
        zf.writestr("note/README.md", b"non e una fattura")
    response = client.post(
        "/api/eye/invoices/import/preview-batch",
        files=[("files", ("fatture.zip", archive.getvalue(), "application/zip"))],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] == 2
    assert payload["failed"] == 0
    assert {item["filename"] for item in payload["items"]} == {"fattura-1.xml", "fattura-2.xml"}
