from datetime import date
from pathlib import Path

from app.config import settings
from app.models import ImportJob, Invoice, InvoiceRow, Supplier


def _invoice(db, *, filename="sample.xml", digest="a" * 64):
    supplier = Supplier(ragione_sociale="Fornitore Test Locale")
    db.add(supplier)
    db.flush()
    invoice = Invoice(supplier_id=supplier.id, numero="FT-123", data=date(2026, 10, 1),
                      file_originale=filename, hash_file=digest)
    db.add(invoice)
    db.flush()
    db.add(InvoiceRow(invoice_id=invoice.id, descrizione_originale="Latte intero 1 litro",
                      descrizione_normalizzata="latte intero", quantita=1, prezzo_unitario=2,
                      totale_riga=2))
    db.commit()
    return invoice


def test_invoice_file_search_by_product_and_supplier(client, db):
    invoice = _invoice(db)
    by_product = client.get("/api/eye/invoice-files", params={"q": "Latte"})
    assert by_product.status_code == 200
    assert [item["id"] for item in by_product.json()["items"]] == [invoice.id]
    by_supplier = client.get("/api/eye/invoice-files", params={"q": "Fornitore Test"})
    assert by_supplier.status_code == 200
    assert [item["id"] for item in by_supplier.json()["items"]] == [invoice.id]
    assert by_product.json()["items"][0]["available"] is False


def test_download_only_original_xml_from_uploads(client, db):
    invoice = _invoice(db, filename="originale.xml")
    source = settings.data_dir / "uploads" / "originale.xml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("<FatturaElettronica>test</FatturaElettronica>", encoding="utf-8")
    response = client.get(f"/api/eye/invoice-files/{invoice.id}/original")
    assert response.status_code == 200
    assert response.content == source.read_bytes()
    source.unlink()


def test_invoice_file_download_rejects_outside_upload_directory(client, db, tmp_path):
    invoice = _invoice(db, filename="outside.xml", digest="b" * 64)
    external = tmp_path / "outside.xml"
    external.write_text("<FatturaElettronica/>", encoding="utf-8")
    db.add(ImportJob(filename="outside.xml", stored_path=str(external),
                     file_hash=invoice.hash_file, status="completed"))
    db.commit()
    response = client.get(f"/api/eye/invoice-files/{invoice.id}/original")
    assert response.status_code == 404
