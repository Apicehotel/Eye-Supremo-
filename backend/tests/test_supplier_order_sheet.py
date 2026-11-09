"""Foglio ordini fornitore: file e dati inventati (il foglio reale non va nel repository)."""
import io
from datetime import datetime

import openpyxl
import pytest

from app.supplier_order_sheet import article_page, build_sheet_views, parse_order_workbook


def make_workbook() -> bytes:
    wb = openpyxl.Workbook()
    d = wb.active; d.title = "Dettaglio articoli"
    d.append(["Articolo (Descrizione)", "Quantità", "UM", "Data ordine", "Cod. articolo", "N. ordine", "N. fattura", "Data fattura", "Tipo documento", "Note"])
    d.append(["ACQUA NATURALE 24X50CL", 2, "N.", datetime(2026, 5, 4), "A1", "O1", "F1", datetime(2026, 5, 5), "Fattura", None])
    d.append(["ACQUA NATURALE 24X50CL", 2, "N.", None, "A1", "O2", "F2", datetime(2026, 6, 2), "Fattura", None])
    d.append(["ACQUA NATURALE 24X50CL", -1, "N.", None, "A1", "O3", "F3", datetime(2026, 6, 20), "Nota di credito", None])
    d.append(["AMARETTI 250G", 6, "N.", datetime(2026, 5, 4), "B2", "O1", "F1", datetime(2026, 5, 5), "Fattura", None])
    p = wb.create_sheet("Prezzi da fatture")
    for _ in range(4): p.append([None])
    p.append(["Data fattura", "Numero fattura", "Data DDT", "Tipo doc.", "Codice articolo", "Descrizione", "Quantità", "UM", "Prezzo unit.", "Totale riga", "IVA %", "Riga origine", "Scheda", "Cella", "File XML", "Riga fattura"])
    p.append([datetime(2026, 5, 5), "F1", datetime(2026, 5, 5), "TD24", "A1", "ACQUA NATURALE 24X50CL", 2, "N.", 6.0, 12.0, 10, 2, "x", "B7", "a.xml", 1])
    p.append([datetime(2026, 5, 5), "F1", datetime(2026, 5, 5), "TD24", "B2", "AMARETTI 250G", 6, "N.", 3.0, 18.0, 10, 5, "x", "B7", "a.xml", 2])
    r = wb.create_sheet("Fatture ricevute")
    for _ in range(3): r.append([None])
    r.append(["Data", "Numero", "DDT", "Tipo", "Righe", "Imponibile", "IVA", "Totale", "XML", "Esito", "Diff"])
    r.append([datetime(2026, 5, 5), "F1", datetime(2026, 5, 5), "TD24", None, None, 3.0, 33.0, "a.xml", None, None])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def views():
    return build_sheet_views(parse_order_workbook(make_workbook()))


def test_parse_reads_the_three_sheets():
    data = parse_order_workbook(make_workbook())
    assert (len(data["movements"]), len(data["prices"]), len(data["invoices"])) == (4, 2, 1)


def test_checks_match_the_formulas_of_the_sheet():
    c = views()["checks"]
    assert (c["distinct_articles"], c["movements"], c["undated_movements"], c["credit_notes"]) == (2, 4, 2, 1)
    assert c["invoices_balanced"] == 1 and c["quantity_mismatches"] == 0
    assert c["missing_prices"] == 2 and c["missing_xml_invoices"] == 2   # F2 e F3 senza XML


def test_summary_uses_code_net_quantity_and_order_dates():
    water = next(r for r in views()["summary"] if r["code"] == "A1")
    assert water["net_quantity"] == 3 and water["credited_quantity"] == -1 and water["rows"] == 3
    assert (water["first_date"], water["last_date"]) == ("2026-05-04", "2026-05-04")


def test_daily_deliveries_use_invoice_date_when_order_date_missing_and_carry_price():
    water = next(r for r in views()["deliveries"]["rows"] if r["code"] == "A1")
    assert water["days"] == {"2026-05-04": 2, "2026-06-02": 2, "2026-06-20": -1}
    assert water["prices"] == {"2026-05-04": 6.0}
    assert sorted(water["invoice_date_days"]) == ["2026-06-02", "2026-06-20"]


def test_registry_reconciles_like_the_sheet():
    inv = views()["invoices"][0]
    assert (inv["rows_amount"], inv["difference"], inv["outcome"]) == (30.0, 0.0, "OK")


def test_verify_rows_list_undated_and_credit_movements():
    reasons = {r["reason"] for r in views()["checks"]["verify_rows"]}
    assert reasons == {"Senza data ordine", "Senza data ordine / Nota di credito"}


def test_article_page_and_bad_file():
    page = article_page(parse_order_workbook(make_workbook()), "A1")
    assert page["net_quantity"] == 3 and page["without_order_date"] == 2
    with pytest.raises(ValueError):
        wb = openpyxl.Workbook(); buf = io.BytesIO(); wb.save(buf); parse_order_workbook(buf.getvalue())


def test_import_and_read_endpoints(client):
    c, h = client, {"X-Eye-Role": "developer"}
    r = c.post("/api/eye/central/supplier-orders/import?supplier=Fornitore%20Prova", files={"file": ("o.xlsx", make_workbook())}, headers=h)
    assert r.status_code == 200 and r.json()["movements"] == 4
    got = c.get("/api/eye/central/supplier-orders?supplier=FORNITORE%20PROVA", headers=h).json()
    assert got["source"] == "sheet" and got["checks"]["movements"] == 4
    art = c.get("/api/eye/central/supplier-orders/article?supplier=Fornitore%20Prova&code=A1", headers=h).json()
    assert art["net_quantity"] == 3
    assert c.post("/api/eye/central/supplier-orders/import?supplier=X", files={"file": ("o.xlsx", b"nope")}, headers=h).status_code == 400
