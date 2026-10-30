from datetime import date
from decimal import Decimal

from app.models import Invoice, InvoiceRow, Product, Supplier
from app.report_service import historical_product_report


def _row(db, product, description, price, day, number):
    supplier = db.query(Supplier).filter_by(ragione_sociale="Fornitore Test").first()
    if not supplier:
        supplier = Supplier(ragione_sociale="Fornitore Test")
        db.add(supplier)
        db.flush()
    invoice = Invoice(supplier_id=supplier.id, numero=number, data=day, imponibile=Decimal("10"),
                      iva=Decimal("0"), totale=Decimal("10"), hash_file=f"hash-{number}")
    db.add(invoice)
    db.flush()
    db.add(InvoiceRow(invoice_id=invoice.id, product_id=product.id, descrizione_originale=description,
                      descrizione_normalizzata=description.lower(), quantita=Decimal("10"),
                      unita_normalizzata="pz", prezzo_unitario=Decimal(str(price)), totale_riga=Decimal(str(price * 10))))


def test_search_by_brand_finds_rows_whose_description_omits_the_brand(db):
    product = Product(nome_canonico="Succo Pago Ace", marca="Pago")
    db.add(product)
    db.flush()
    _row(db, product, "SUCCO ACE 200ML X24", 0.55, date(2026, 5, 2), "B-1")
    db.commit()

    report = historical_product_report(db, "pago")
    assert report["suppliers"], "la ricerca per marca non deve restituire un report vuoto"
    assert report["suppliers"][0]["observations"] == 1


def test_search_by_canonical_name_finds_abbreviated_invoice_descriptions(db):
    product = Product(nome_canonico="Mozzarella Fior di Latte")
    db.add(product)
    db.flush()
    _row(db, product, "FIORDILATTE TAGLIATA 1KG", 6.2, date(2026, 5, 3), "M-1")
    db.commit()

    report = historical_product_report(db, "mozzarella")
    assert report["suppliers"], "il nome canonico del prodotto collegato deve bastare per trovare la riga"


def test_unlinked_unrelated_rows_are_still_rejected(db):
    product = Product(nome_canonico="Detersivo Piatti")
    db.add(product)
    db.flush()
    _row(db, product, "DETERSIVO PIATTI 5LT", 4.0, date(2026, 5, 4), "D-1")
    db.commit()

    report = historical_product_report(db, "pago")
    assert not report["suppliers"]
