"""Costi extra per fornitore: righe fattura che non sono prodotti (carburante, accise, trasporto, sconti,
bollo, CONAI, resi, servizi, riferimenti, importi negativi, righe a 0 €).

Classificazione per parole chiave sulla descrizione, in ordine di priorità: è una stima per leggere i costi,
non cambia le descrizioni né lo stato delle righe. Le stesse regole sono state provate in SQL sul centrale.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy.orm import Session

from .supplier_orders import known_invoices

# (chiave, etichetta, regex) in ordine di priorità: la prima che combacia vince.
CATEGORIES: list[tuple[str, str, re.Pattern]] = [
    ("fuel", "Carburante", re.compile(r"carburant|gasolio|benzina|diesel|gpl|metano|self service|servito")),
    ("excise", "Accise", re.compile(r"accis")),
    ("transport", "Trasporto / consegna", re.compile(r"trasporto|spedizion|consegna|corriere|spese di")),
    ("discounts", "Sconti / omaggi / abbuoni", re.compile(r"sconto|abbuono|omaggio|premio|bonus")),
    ("stamp", "Bollo", re.compile(r"bollo")),
    ("packaging", "Cauzioni / imballi / CONAI", re.compile(r"cauzione|vuoto a rendere|vuoti|pallet|bancale|epal|conai|imballo")),
    ("credits", "Resi / storni", re.compile(r"reso|rettifica|storno|nota di credito|nota credito|accredito|errata")),
    ("services", "Servizi / canoni / utenze", re.compile(r"canone|abbonamento|licenza|assistenza|manutenzione|noleggio|affitto|energia|telefon|polizza|assicuraz")),
    ("reference", "Riferimenti documento", re.compile(r"ddt|d\.d\.t|riferimento|ordine n|vs\. ordine|fattura n")),
]
LABELS = {key: label for key, label, _ in CATEGORIES}
LABELS.update({"negative": "Importi negativi (acconti, arrotondamenti…)", "zero": "Righe a 0 € (descrittive)"})


def classify_row(description: str, quantity: float, unit_price: float, line_total: float) -> str | None:
    """Categoria extra della riga, oppure None se è un prodotto normale."""
    text = (description or "").lower()
    for key, _, pattern in CATEGORIES:
        if pattern.search(text):
            return key
    if quantity < 0 or line_total < 0:
        return "negative"
    if not unit_price and not line_total:
        return "zero"
    return None


def _n(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_supplier_extras(invoices: list[dict]) -> dict:
    cats: dict[str, dict] = {}
    product_total = 0.0
    product_rows = 0
    for invoice in invoices:
        for row in invoice.get("rows") or []:
            description = str(row.get("original_description") or row.get("normalized_description") or "").strip()
            quantity, price, total = _n(row.get("quantity")), _n(row.get("unit_price")), _n(row.get("line_total"))
            key = classify_row(description, quantity, price, total)
            if key is None:
                product_total += total
                product_rows += 1
                continue
            entry = cats.setdefault(key, {"key": key, "label": LABELS[key], "rows": 0, "total": 0.0, "invoices": set(), "top": defaultdict(lambda: [0, 0.0])})
            entry["rows"] += 1
            entry["total"] += total
            entry["invoices"].add(invoice.get("invoice_number"))
            top = entry["top"][description[:120] or "(senza descrizione)"]
            top[0] += 1
            top[1] += total
    order = [key for key, _, _ in CATEGORIES] + ["negative", "zero"]
    items = []
    for key in order:
        entry = cats.get(key)
        if not entry:
            continue
        top = sorted(entry["top"].items(), key=lambda kv: (-abs(kv[1][1]), -kv[1][0]))[:5]
        items.append({
            "key": key, "label": entry["label"], "rows": entry["rows"], "total": round(entry["total"], 2),
            "invoices": len(entry["invoices"]),
            "top": [{"description": d, "rows": v[0], "total": round(v[1], 2)} for d, v in top],
        })
    return {
        "categories": items,
        "extra_total": round(sum(i["total"] for i in items), 2),
        "extra_rows": sum(i["rows"] for i in items),
        "product_total": round(product_total, 2),
        "product_rows": product_rows,
        "note": "Stima per parole chiave sulla descrizione; le righe restano quelle originali.",
    }


def supplier_extras(db: Session, supplier_name: str) -> dict:
    return build_supplier_extras(known_invoices(db, supplier_name))
