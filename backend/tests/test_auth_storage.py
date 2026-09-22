"""Auth locale + upload Storage con controllo doppioni (mirror locale)."""
from pathlib import Path

from app.models import Invoice, Supplier
from app.services import create_invoice
from app.schemas import InvoiceIn, RowIn
from datetime import date
from decimal import Decimal


def _bootstrap(client, pin="123456"):
    res = client.post("/api/auth/bootstrap", json={"pin": pin})
    assert res.status_code == 200, res.text
    return res.json()


def _login(client, username, pin):
    res = client.post("/api/auth/login", json={"username": username, "pin": pin})
    assert res.status_code == 200, res.text
    return res.json()


def test_bootstrap_and_uploader_sees_only_own_flow(client, db):
    boot = _bootstrap(client)
    assert boot["user"]["role_name"] == "developer"
    headers = {"X-Eye-Session": boot["session"]}

    # Imposta PIN caricatore
    users = client.get("/api/auth/users", headers=headers).json()
    caricatore = next(u for u in users if u["username"] == "caricatore")
    set_pin = client.put(f"/api/auth/users/{caricatore['id']}/pin", headers=headers, json={"pin": "654321"})
    assert set_pin.status_code == 200, set_pin.text

    up = _login(client, "caricatore", "654321")
    up_headers = {"X-Eye-Session": up["session"]}
    assert up["user"]["role_name"] == "uploader"

    xml = Path("tests/fixtures/fattura.xml").read_bytes()
    files = {"file": ("fattura.xml", xml, "application/xml")}
    uploaded = client.post("/api/storage/upload", headers=up_headers, files=files)
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["backend"] == "local_mirror"
    assert body["upload"]["status"] == "pending_review"
    path = body["upload"]["storage_path"]
    assert path.startswith("invoices/xml/")
    assert path.endswith(".xml")
    assert body["upload"]["file_hash"][:2] in path
    assert body["upload"]["file_hash"] in path

    inbox_uploader = client.get("/api/storage/inbox", headers=up_headers).json()
    assert len(inbox_uploader) == 1

    supplier = Supplier(ragione_sociale="Demo SPA", partita_iva="IT000")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    create_invoice(
        db,
        InvoiceIn(
            supplier_id=supplier.id,
            numero="DUP-1",
            data=date(2024, 1, 1),
            imponibile=Decimal("10"),
            iva=Decimal("2"),
            totale=Decimal("12"),
            hash_file=body["upload"]["file_hash"],
            rows=[
                RowIn(
                    descrizione_originale="Voce",
                    descrizione_normalizzata="voce",
                    quantita=Decimal("1"),
                    prezzo_unitario=Decimal("10"),
                    totale_riga=Decimal("10"),
                )
            ],
        ),
    )

    uploaded2 = client.post("/api/storage/upload", headers=up_headers, files=files)
    assert uploaded2.status_code == 200, uploaded2.text
    assert uploaded2.json()["upload"]["status"] == "possible_duplicate"
    assert uploaded2.json()["duplicate_matches"]


def test_operator_inbox_and_reject(client):
    boot = _bootstrap(client)
    headers = {"X-Eye-Session": boot["session"]}
    users = client.get("/api/auth/users", headers=headers).json()
    caricatore = next(u for u in users if u["username"] == "caricatore")
    client.put(f"/api/auth/users/{caricatore['id']}/pin", headers=headers, json={"pin": "654321"})
    up = _login(client, "caricatore", "654321")
    up_headers = {"X-Eye-Session": up["session"]}

    xml = Path("tests/fixtures/fattura.xml").read_bytes()
    uploaded = client.post(
        "/api/storage/upload",
        headers=up_headers,
        files={"file": ("fattura.xml", xml, "application/xml")},
    ).json()
    upload_id = uploaded["upload"]["id"]

    inbox = client.get("/api/storage/inbox", headers=headers).json()
    assert any(x["id"] == upload_id for x in inbox)

    # Uploader cannot reject
    denied = client.post(f"/api/storage/{upload_id}/reject", headers=up_headers)
    assert denied.status_code == 403

    rejected = client.post(f"/api/storage/{upload_id}/reject", headers=headers)
    assert rejected.status_code == 200


def test_central_requires_config(client):
    boot = _bootstrap(client)
    headers = {"X-Eye-Session": boot["session"]}
    res = client.get("/api/storage/central", headers=headers)
    assert res.status_code == 503


def test_build_storage_path_convention():
    from app.storage_service import build_storage_path, resolve_blob_path

    digest = "30ed1ecb27af6bd9757a864c3c51d0077942865462dbb16f431fd75c40c8f6a9"
    path = build_storage_path("IT03618500403_41sVr.xml", digest)
    assert path == f"invoices/xml/30/{digest}.xml"
    assert resolve_blob_path(digest, "xml") == path
    pdf = build_storage_path("fattura.pdf", digest)
    assert pdf == f"invoices/pdf/30/{digest}.pdf"
