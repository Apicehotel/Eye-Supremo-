from datetime import date
from unittest.mock import AsyncMock, patch

from app.models import Invoice, InvoiceRow, Supplier
from app.services import answer_with_ollama, search_records


def test_search_records_includes_row_total(db):
    supplier = Supplier(ragione_sociale="Fornitore Test")
    db.add(supplier)
    db.flush()
    invoice = Invoice(
        supplier_id=supplier.id,
        numero="LEG-1",
        data=date(2026, 3, 1),
        imponibile=110,
        iva=22,
        totale=132,
    )
    db.add(invoice)
    db.flush()
    db.add_all(
        [
            InvoiceRow(
                invoice_id=invoice.id,
                descrizione_originale="Lampadina LED",
                descrizione_normalizzata="lampadina led",
                quantita=2,
                prezzo_unitario=5,
                totale_riga=10,
                confidence=1,
            ),
            InvoiceRow(
                invoice_id=invoice.id,
                descrizione_originale="Carta igienica",
                descrizione_normalizzata="carta igienica",
                quantita=10,
                prezzo_unitario=10,
                totale_riga=100,
                confidence=1,
            ),
        ]
    )
    db.commit()
    records = search_records(db, "lampadina", limit=20)
    assert len(records) == 1
    assert records[0]["totale_riga"] == 10.0


def test_legacy_ask_sums_matching_rows_not_invoice_total(db):
    import asyncio

    supplier = Supplier(ragione_sociale="Fornitore Test")
    db.add(supplier)
    db.flush()
    invoice = Invoice(
        supplier_id=supplier.id,
        numero="LEG-2",
        data=date(2026, 3, 1),
        imponibile=110,
        iva=22,
        totale=132,
    )
    db.add(invoice)
    db.flush()
    db.add_all(
        [
            InvoiceRow(
                invoice_id=invoice.id,
                descrizione_originale="Lampadina LED",
                descrizione_normalizzata="lampadina led",
                quantita=2,
                prezzo_unitario=5,
                totale_riga=10,
                confidence=1,
            ),
            InvoiceRow(
                invoice_id=invoice.id,
                descrizione_originale="Carta igienica",
                descrizione_normalizzata="carta igienica",
                quantita=10,
                prezzo_unitario=10,
                totale_riga=100,
                confidence=1,
            ),
        ]
    )
    db.commit()
    records = search_records(db, "quanto abbiamo speso per lampadina", limit=20)

    async def _run():
        with patch(
            "app.services.ollama_status",
            new=AsyncMock(return_value={"available": False, "models": [], "layers": {}}),
        ):
            return await answer_with_ollama("quanto abbiamo speso per lampadina", records, db)

    result = asyncio.run(_run())
    assert result["mode"] == "deterministic"
    assert "10,00" in result["answer"]
    assert "132" not in result["answer"]
