from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .models import AppSetting, Invoice, InvoiceRow, InvoiceRowPolicy, Product, Supplier
from .normalization import extract_content, normalize_text, normalize_unit
from .product_taxonomy import extract_product_query, is_product_search_match, product_stem, row_matches_product_query, search_terms


def _money(value) -> float:
    return round(float(value or 0), 4)


def _comparable_quantity(row: InvoiceRow, unit: str) -> float:
    """Show the quantity behind the normalized price, not the package label."""
    quantity = _money(row.quantita)
    content_qty, content_unit, content_in_base = extract_content(row.descrizione_originale or "")
    original_unit = normalize_unit(row.unita_originale)[0] if row.unita_originale else None
    if content_in_base and content_unit == unit and original_unit in {None, "confezione", "scatola", "rotolo"}:
        return _money(Decimal(str(quantity)) * content_in_base)
    return quantity


def _point_order(point: dict) -> tuple:
    row_id = point.get("row_id")
    return (point["date"], isinstance(row_id, str), row_id if isinstance(row_id, int) else 0, str(row_id))


def _config_for_row(configs: dict, row: InvoiceRow, product: Product | None) -> dict | None:
    if product and product.nome_canonico and isinstance(configs.get(product.nome_canonico), dict):
        return configs[product.nome_canonico]
    # Le righe importate possono non avere ancora product_id. In quel caso la
    # configurazione salvata dalla schermata Prodotti deve comunque applicarsi
    # alla descrizione originale della fattura.
    description = normalize_text(row.descrizione_originale or row.descrizione_normalizzata or "")
    for source_name, config in configs.items():
        if isinstance(config, dict) and normalize_text(str(source_name)) == description:
            return config
    return None


def _cache_complete(db: Session) -> bool | None:
    """True/False se la cache fatture è stata verificata completa/incompleta, None se non verificata."""
    row = db.get(AppSetting, "central_sync_complete")
    value = row.value if row else None
    return True if value == "yes" else False if value == "no" else None


def _cache_observations(db: Session, product_query: str) -> list[dict]:
    """Righe prodotto della cache PC (fatture centrali scaricate) per lo storico, senza tetto."""
    try:
        from .central_cache import cached_row_search

        items = cached_row_search(db, product_query, limit=None).get("items", [])
    except Exception:  # noqa: BLE001 - la cache non deve mai rompere il report
        return []
    out: list[dict] = []
    for item in items:
        if item.get("analysis_status") not in (None, "product"):
            continue
        description = str(item.get("original_description") or item.get("normalized_description") or "")
        if not row_matches_product_query(description, product_query):
            continue
        if not is_product_search_match(description, product_query):
            continue
        raw = item.get("normalized_price")
        price = _money(raw if raw not in (None, 0, "0") else item.get("unit_price"))
        if price <= 0 or not item.get("invoice_date"):
            continue
        out.append({
            "row_id": item.get("id"),
            "hash": str(item.get("source_hash") or item.get("id")),
            "supplier": str(item.get("supplier_name") or "Fornitore"),
            "invoice": str(item.get("invoice_number") or ""),
            "date": str(item.get("invoice_date"))[:10],
            "price": price,
            "quantity": _money(item.get("quantity")),
            "unit": str(item.get("normalized_unit") or item.get("original_unit") or "pz").lower(),
            "description": description,
        })
    return out


def historical_product_report(db: Session, query: str, limit: int | None = None) -> dict:
    # Estrae il prodotto dalla domanda («chi mi vende meglio i bomboloni» → bomboloni).
    product_query = extract_product_query(query) or normalize_text(query)
    q = normalize_text(product_query)
    if not q:
        return {"query": query, "summary": None, "suppliers": [], "dates": [], "units": []}

    semantic_terms = tuple(dict.fromkeys(search_terms(q) + (q,)))
    text_fields = (InvoiceRow.descrizione_normalizzata, InvoiceRow.descrizione_originale, Product.nome_canonico, Product.marca)
    semantic_clauses = []
    for term in semantic_terms:
        tokens = normalize_text(term).split()
        if not tokens:
            continue
        # Match every meaningful word independently. This handles supplier
        # abbreviations such as "c igienica" and descriptions with extra
        # package/brand text between the words.
        semantic_clauses.append(and_(*[or_(*[field.ilike(f"%{token}%") for field in text_fields]) for token in tokens]))
    stem = product_stem(q)
    if stem and len(stem) >= 6:
        # Cattura «MINIBOMBOLONI» come unica parola, senza aprire a bombola.
        semantic_clauses.append(or_(*[field.ilike(f"%{stem}%") for field in text_fields]))
    if not semantic_clauses:
        return {"query": query, "summary": None, "suppliers": [], "dates": [], "units": []}
    stmt = (
        select(InvoiceRow, Invoice, Supplier, Product, InvoiceRowPolicy)
        .join(Invoice, Invoice.id == InvoiceRow.invoice_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(Product, Product.id == InvoiceRow.product_id)
        .outerjoin(InvoiceRowPolicy, InvoiceRowPolicy.row_id == InvoiceRow.id)
        .where(
            or_(*semantic_clauses)
        )
        .where(or_(InvoiceRowPolicy.analysis_status.is_(None), InvoiceRowPolicy.analysis_status == "product"))
        .order_by(Invoice.data.asc(), InvoiceRow.id.asc())
    )
    # Nessun tetto: storico su tutte le osservazioni dell'archivio.
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit)
    records = db.execute(stmt).all()

    config_row = db.get(AppSetting, "product_configs")
    try:
        product_configs = json.loads(config_row.value) if config_row and config_row.value else {}
    except (TypeError, ValueError):
        product_configs = {}
    if not isinstance(product_configs, dict):
        product_configs = {}

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    supplier_names: dict[str, str] = {}
    supplier_ids: dict[str, object] = {}
    manufacturers: set[str] = set()
    product_names: list[str] = []
    local_hashes: set[str] = set()
    local_invoice_keys: set[tuple[str, str, str]] = set()
    local_points = 0
    for row, invoice, supplier, product, _policy in records:
        description = row.descrizione_originale or row.descrizione_normalizzata or ""
        if not is_product_search_match(description, product_query):
            continue
        unit = (row.unita_normalizzata or row.unita_originale or (product.unita_base if product else None) or "pz").lower()
        raw_price = row.prezzo_normalizzato if row.prezzo_normalizzato not in (None, Decimal("0")) else row.prezzo_unitario
        price = _money(raw_price)
        product_config = _config_for_row(product_configs, row, product)
        pieces = float(product_config.get("pieces_per_pack") or 0) if isinstance(product_config, dict) else 0
        if pieces > 0 and row.prezzo_unitario:
            price = _money(Decimal(str(row.prezzo_unitario)) / Decimal(str(pieces)))
            unit = str(product_config.get("normalization_unit") or "pz")
        if price <= 0:
            continue
        manufacturer = (product.marca if product and product.marca else "").strip()
        if manufacturer:
            manufacturers.add(manufacturer)
        if product and product.nome_canonico:
            product_names.append(product.nome_canonico)
        skey = normalize_text(supplier.ragione_sociale)
        supplier_names.setdefault(skey, supplier.ragione_sociale)
        supplier_ids.setdefault(skey, supplier.id)
        if invoice.hash_file:
            local_hashes.add(invoice.hash_file)
        local_invoice_keys.add((skey, normalize_text(invoice.numero), invoice.data.isoformat()))
        local_points += 1
        grouped[(skey, unit)].append({
            "row_id": row.id,
            "invoice_id": invoice.id,
            "invoice": invoice.numero,
            "date": invoice.data.isoformat(),
            "price": price,
            "quantity": _comparable_quantity(row, unit),
            "unit": unit,
            "description": row.descrizione_originale,
            "manufacturer": manufacturer or None,
            "source": "local",
        })

    # Fatture scaricate nella cache del PC (archivio centrale): senza questo il report
    # vedeva solo le fatture importate in locale e mostrava un solo fornitore.
    cache_points = 0
    cache_rows = _cache_observations(db, product_query)
    for item in cache_rows:
        skey = normalize_text(item["supplier"])
        if item["hash"] in local_hashes or (skey, normalize_text(item["invoice"]), item["date"]) in local_invoice_keys:
            continue  # stessa fattura già presente in locale
        supplier_names.setdefault(skey, item["supplier"])
        supplier_ids.setdefault(skey, item["supplier"])
        cache_points += 1
        grouped[(skey, item["unit"])].append({
            "row_id": item["row_id"],
            "invoice_id": item["hash"],
            "invoice": item["invoice"],
            "date": item["date"],
            "price": item["price"],
            "quantity": item["quantity"],
            "unit": item["unit"],
            "description": item["description"],
            "manufacturer": None,
            "source": "cache",
        })

    supplier_blocks = []
    all_points = []
    for (skey, unit), points in grouped.items():
        points.sort(key=_point_order)
        previous = None
        for point in points:
            delta = None if previous is None else round(point["price"] - previous, 4)
            pct = None if previous in (None, 0) else round((point["price"] - previous) / previous * 100, 2)
            point["delta"] = delta
            point["delta_pct"] = pct
            point["trend"] = "initial" if previous is None else ("up" if delta > 0 else "down" if delta < 0 else "same")
            previous = point["price"]
        prices = [p["price"] for p in points]
        best_point = min(points, key=lambda p: p["price"])
        latest = points[-1]
        block = {
            "supplier_id": supplier_ids.get(skey),
            "supplier": supplier_names.get(skey) or skey,
            "unit": unit,
            "manufacturer": next((p["manufacturer"] for p in points if p["manufacturer"]), None),
            "initial_price": prices[0],
            "initial_date": points[0]["date"],
            "average_price": round(sum(prices) / len(prices), 4),
            "best_price": best_point["price"],
            "best_date": best_point["date"],
            "latest_price": latest["price"],
            "latest_date": latest["date"],
            "observations": len(points),
            "points": points,
        }
        supplier_blocks.append(block)
        all_points.extend([(block, p) for p in points])

    if not supplier_blocks:
        return {"query": query, "summary": None, "suppliers": [], "dates": [], "units": []}

    # Do not compare unlike units. The dominant unit is the one with the most observations.
    unit_counts: dict[str, int] = defaultdict(int)
    for block in supplier_blocks:
        unit_counts[block["unit"]] += block["observations"]
    dominant_unit = max(unit_counts, key=unit_counts.get)
    comparable = [b for b in supplier_blocks if b["unit"] == dominant_unit]
    comparable_points = [p for b, p in all_points if b["unit"] == dominant_unit]
    first_point = min(comparable_points, key=_point_order)
    last_point = max(comparable_points, key=_point_order)
    best_point = min(comparable_points, key=lambda p: p["price"])
    best_supplier = min(comparable, key=lambda b: b["average_price"])
    summary = {
        "product": product_names[0] if product_names else query.strip(),
        "manufacturers": sorted(manufacturers),
        "unit": dominant_unit,
        "initial_price": first_point["price"],
        "initial_date": first_point["date"],
        "average_price": round(sum(p["price"] for p in comparable_points) / len(comparable_points), 4),
        "best_price": best_point["price"],
        "best_date": best_point["date"],
        "latest_price": last_point["price"],
        "latest_date": last_point["date"],
        "best_supplier": best_supplier["supplier"],
        "best_supplier_average": best_supplier["average_price"],
        "best_supplier_observations": best_supplier["observations"],
    }
    dates = sorted({p["date"] for block in comparable for p in block["points"]})
    supplier_blocks.sort(key=lambda b: (b["unit"] != dominant_unit, b["average_price"], b["supplier"].lower()))
    return {
        "query": query,
        "summary": summary,
        "suppliers": supplier_blocks,
        "dates": dates,
        "units": sorted(unit_counts),
        "comparison_note": "I confronti tra fornitori usano solo prezzi con la stessa unità normalizzata.",
        "sources": {"local": local_points, "cache": cache_points, "suppliers": len(supplier_blocks), "cache_complete": _cache_complete(db)},
    }
