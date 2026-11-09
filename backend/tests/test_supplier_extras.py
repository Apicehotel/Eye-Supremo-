"""Costi extra per fornitore: righe inventate."""
from app.supplier_extras import build_supplier_extras, classify_row


def row(desc, qty=1, price=1.0, total=None):
    return {"original_description": desc, "quantity": qty, "unit_price": price, "line_total": price * qty if total is None else total}


def test_classify_priority_and_defaults():
    assert classify_row("BENZINA S.PB 10 PPM", 1, 50, 50) == "fuel"
    assert classify_row("Accisa sull'energia elettrica", 1, 10, 10) == "excise"
    assert classify_row("Contributo CONAI assolto", 1, 1, 1) == "packaging"
    assert classify_row("Addebito imposta di bollo", 1, 2, 2) == "stamp"
    assert classify_row("Canone assistenza software", 1, 100, 100) == "services"
    assert classify_row("ACCONTO PAGATO", 1, -50, -50) == "negative"
    assert classify_row("Testo di accompagnamento", 1, 0, 0) == "zero"
    assert classify_row("ACQUA NATURALE 24X50CL", 2, 6, 12) is None
    # il carburante vince su «servizi» e sul resto
    assert classify_row("Servizio self service gasolio", 1, 40, 40) == "fuel"


def test_build_groups_totals_and_top_descriptions():
    invoices = [
        {"invoice_number": "F1", "rows": [row("ACQUA", 2, 6), row("GASOLIO AUTO", 1, 60), row("Trasporto prodotti", 1, 15)]},
        {"invoice_number": "F2", "rows": [row("GASOLIO AUTO", 1, 70), row("Descrizione libera", 1, 0, 0), row("SCONTO", 1, -5, -5)]},
    ]
    data = build_supplier_extras(invoices)
    cats = {c["key"]: c for c in data["categories"]}
    assert cats["fuel"]["rows"] == 2 and cats["fuel"]["total"] == 130 and cats["fuel"]["invoices"] == 2
    assert cats["fuel"]["top"][0] == {"description": "GASOLIO AUTO", "rows": 2, "total": 130.0}
    assert cats["transport"]["total"] == 15 and cats["discounts"]["total"] == -5 and cats["zero"]["rows"] == 1
    assert data["product_total"] == 12 and data["product_rows"] == 1
    assert data["extra_total"] == 140 and data["extra_rows"] == 5


def test_empty_supplier_and_endpoint(client):
    assert build_supplier_extras([])["categories"] == []
    r = client.get("/api/eye/central/supplier-extras?supplier=Nessuno", headers={"X-Eye-Role": "developer"})
    assert r.status_code == 200 and r.json()["extra_rows"] == 0
