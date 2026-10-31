import asyncio
import logging
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Hotel, Invoice, InvoiceMeta
from ..central_service import central_invoice_search, central_product_detail, central_product_page
import json

from ..models import AppSetting
from ..normalization import normalize_text
from ..product_recognition import annotate as annotate_recognition, collapse_to_product, set_user_groups
from ..product_variants import annotate_variants, sort_variants, variant_info
from ..product_taxonomy import is_catalog_product, is_family_match, is_product_search_match, merge_product_catalog, search_terms
from ..report_service import historical_product_report, local_variant_matches, report_from_entries

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/eye", tags=["Eye Supremo reports"])

def _with_variants(items):
    """Aggiunge gusto/grammatura e ordina le varianti di una famiglia (marmellate per gusto e peso)."""
    return sort_variants(annotate_variants(items))



@router.get("/reports/history-product")
async def history_product(q: str = Query(min_length=1, max_length=180), db: Session = Depends(get_db)):
    result = historical_product_report(db, q)
    # Family searches must pass through the same semantic guards for both the
    # local database and the central catalogue. Otherwise an old local broad
    # match could reintroduce ``lampada`` when the user asked for ``lampadine``.
    normalized_query = q.strip().lower()
    if result.get("summary") and normalized_query not in {"lampadine", "a4", "carta a4", "acqua"}:
        # Gusti o formati diversi non vanno mescolati in un solo storico: prima si sceglie la variante.
        variants = local_variant_matches(result)
        if variants:
            return {**result, "summary": None, "suppliers": [], "dates": [], "matches": sort_variants(variants, name_key="canonical_name")}
        return result
    if q.strip().lower() in {"a4", "carta a4"}:
        search_queries = [q]
        responses = await asyncio.gather(*(central_invoice_search(term, 500) for term in search_queries))
        merged_matches = {}
        for response in responses:
            for item in response.get("items", []):
                identity = (item.get("id"), item.get("original_description"), item.get("quantity"), item.get("unit_price"))
                merged_matches[identity] = item
        matches = {"items": list(merged_matches.values())}
        entries = []
        for row in matches.get("items", []):
            if not is_family_match(row.get("original_description") or row.get("normalized_description") or "", q):
                continue
            if row.get("analysis_status") not in (None, "product"):
                continue
            price = row.get("unit_price")
            if price is None or float(price) <= 0:
                continue
            entries.append({"supplier": str(row.get("supplier_name") or "Fornitore"), "unit": str(row.get("normalized_unit") or row.get("original_unit") or "unità").lower(), "date": row.get("invoice_date"), "price": float(price), "quantity": row.get("quantity"), "invoice": row.get("invoice_number"), "invoice_id": row.get("source_hash") or row.get("invoice_id"), "description": row.get("original_description") or q})
        note = "Confronto famiglia Acqua: sono incluse le righe acqua compatibili di tutti i fornitori." if q.strip().lower() == "acqua" else "Confronto famiglia A4: sono incluse le righe prodotto A4 di tutti i fornitori."
        family_report = report_from_entries(q, entries, product=q.strip().upper(), manufacturers=[], note=note)
        if family_report:
            return family_report
    # Local-first installations may have no Invoice rows while the shared
    # catalogue is already populated. Adapt the central product detail to the
    # same report contract used by the Excel-inspired UI.
    report_terms = list(search_terms(q))
    if len(q.split()) > 1:
        report_terms.append(q.split()[0])
    pages = [await central_product_page(term, 2000) for term in dict.fromkeys(report_terms)]
    merged = {}
    for page_item in pages:
        for item in page_item.get("items", []):
            if item.get("nome_canonico") and is_catalog_product(item["nome_canonico"]) and is_product_search_match(item["nome_canonico"], q):
                merged[item["nome_canonico"]] = item
    # The historical report has its own variant picker. Keep it aligned with
    # the product catalogue: equivalent descriptions with the same content
    # must appear as one product, while the source names remain available for
    # the detail/history lookup.
    page = {"items": _with_variants(annotate_recognition(collapse_to_product(merge_product_catalog(list(merged.values()), collapse_family="acqua" if q.strip().lower() == "acqua" else None), q)))}
    product = next((x for x in page["items"] if x.get("nome_canonico")), None)
    if not product:
        # Il catalogo centrale può essere vuoto/non aggiornato mentre le righe
        # delle fatture sono già disponibili nella vista di ricerca centrale.
        # In quel caso non lasciare il report vuoto: usa le righe reali,
        # mantenendo il filtro prodotto per evitare fornitori o descrizioni
        # casualmente simili.
        remote = await central_invoice_search(q, 500)
        rows = []
        for item in remote.get("items", []):
            description = str(item.get("original_description") or item.get("normalized_description") or "").strip()
            if not description or not is_product_search_match(description, q):
                continue
            if item.get("analysis_status") not in (None, "product"):
                continue
            raw_price = item.get("normalized_price") or item.get("unit_price")
            if raw_price is None or float(raw_price) <= 0:
                continue
            rows.append({**item, "description": description, "price": float(raw_price)})
        if not rows:
            return result
        variants = defaultdict(list)
        for row in rows:
            variants[normalize_text(row["description"])].append(row)
        if len(variants) > 1:
            return {
                **result,
                "matches": [
                    {"canonical_name": values[0]["description"], "canonical_names": [values[0]["description"]], "purchases": len(values), "avg_price": round(sum(x["price"] for x in values) / len(values), 4), **variant_info(values[0]["description"])}
                    for values in sorted(variants.values(), key=lambda values: values[0]["description"].lower())
                ],
            }
        product_name = next(iter(variants.values()))[0]["description"]
        pieces, configured_unit = _normalization_config(db, [product_name])
        entries = []
        for row in rows:
            unit = str(row.get("normalized_unit") or row.get("original_unit") or "unità").lower()
            price = row["price"]
            if pieces and row.get("unit_price"):
                price = float(row["unit_price"]) / pieces
                unit = configured_unit
            entries.append({"supplier": str(row.get("supplier_name") or "Fornitore"), "unit": unit, "date": row.get("invoice_date"), "price": price, "quantity": row.get("quantity"), "invoice": row.get("invoice_number"), "invoice_id": row.get("source_hash") or row.get("id"), "description": product_name})
        built = report_from_entries(q, entries, product=product_name, manufacturers=[], note="Storico costruito direttamente sulle righe fattura centrali.")
        if built:
            return built
        return result
    matches = [{"canonical_name": x.get("nome_canonico"), "canonical_names": x.get("canonical_names") or [x.get("nome_canonico")], "brand": x.get("marca"), "purchases": x.get("purchases"), "avg_price": x.get("avg_price"), "recognition": x.get("recognition")} for x in page.get("items", []) if x.get("nome_canonico")]
    matches = sort_variants(annotate_variants(matches, name_key="canonical_name"), name_key="canonical_name")
    # A one-word family search (for example "acqua") is intentionally not
    # collapsed into the first catalogue row: let the user choose the exact
    # product variant so older purchases cannot hide newer ones.
    if len(matches) > 1 and len(q.split()) == 1:
        return {**result, "matches": matches}
    detail_names = product.get("canonical_names") or [product["nome_canonico"]]
    details = await asyncio.gather(*(central_product_detail(name) for name in detail_names))
    history = []
    seen_history = set()
    for detail in details:
        for row in detail.get("history", []):
            identity = (row.get("invoice_id"), row.get("invoice_number"), row.get("invoice_date"), row.get("supplier_name"), row.get("unit_price"), row.get("normalized_price"))
            if identity in seen_history:
                continue
            seen_history.add(identity)
            history.append(row)
    if not history:
        return result
    pieces = _pieces_per_pack(db, [product["nome_canonico"], *detail_names])
    entries = []
    for row in history:
        unit = str(row.get("normalized_unit") or row.get("original_unit") or "unità").lower()
        price = row.get("normalized_price") or row.get("unit_price")
        if pieces and row.get("unit_price"):
            # Pezzi per confezione indicati a mano: normalizza solo il prezzo;
            # la quantità resta quella riportata in fattura.
            price = float(row["unit_price"]) / pieces
            unit = "pz"
        entries.append({"supplier": str(row.get("supplier_name") or "Fornitore"), "unit": unit, "date": row.get("invoice_date"), "price": price, "quantity": row.get("quantity"), "invoice": row.get("invoice_number"), "invoice_id": row.get("source_hash") or row.get("invoice_id"), "description": product["nome_canonico"]})
    built = report_from_entries(q, entries, product=product["nome_canonico"], manufacturer=product.get("marca"), note="I confronti tra fornitori usano solo prezzi con la stessa unità normalizzata.")
    return built or result



def _product_configs(db: Session) -> dict:
    row = db.get(AppSetting, "product_configs")
    try:
        configs = json.loads(row.value) if row and row.value else {}
    except (TypeError, ValueError):
        log.warning("Configurazioni prodotto (product_configs) non leggibili: ignorate", exc_info=True)
        return {}
    return configs if isinstance(configs, dict) else {}


def _normalization_config(db: Session, names: list[str]) -> tuple[float | None, str]:
    """Pezzi per confezione e unità di normalizzazione configurati a mano per uno dei nomi dati."""
    configs = _product_configs(db)
    for name in names:
        config = configs.get(name)
        value = config.get("pieces_per_pack") if isinstance(config, dict) else None
        if value and float(value) > 0:
            return float(value), str(config.get("normalization_unit") or "pz")
    return None, "pz"


def _pieces_per_pack(db: Session, names: list[str]) -> float | None:
    return _normalization_config(db, names)[0]


def _load_groups(db: Session) -> list[list[str]]:
    row = db.get(AppSetting, "product_groups")
    try:
        return json.loads(row.value) if row else []
    except Exception:  # noqa: BLE001
        return []


def _save_groups(db: Session, groups: list[list[str]]) -> list[list[str]]:
    groups = [g for g in groups if len(g) >= 2]
    row = db.get(AppSetting, "product_groups")
    if row:
        row.value = json.dumps(groups, ensure_ascii=False)
    else:
        db.add(AppSetting(key="product_groups", value=json.dumps(groups, ensure_ascii=False)))
    db.commit()
    set_user_groups(groups)
    return groups


@router.get("/product-groups")
def product_groups(db: Session = Depends(get_db)):
    groups = _load_groups(db)
    set_user_groups(groups)
    return groups


@router.post("/product-groups")
def merge_product_names(payload: dict, db: Session = Depends(get_db)):
    """Conferma che questi nomi sono lo stesso prodotto (si uniscono ai gruppi già esistenti)."""
    names = [normalize_text(str(n)) for n in payload.get("names", []) if str(n).strip()]
    names = list(dict.fromkeys(names))
    if len(names) < 2:
        raise HTTPException(400, "Servono almeno due nomi")
    groups = _load_groups(db)
    joined = set(names)
    rest = []
    for g in groups:
        if joined & set(g):
            joined |= set(g)
        else:
            rest.append(g)
    return _save_groups(db, [*rest, sorted(joined)])


@router.delete("/product-groups")
def split_product_name(name: str = Query(min_length=1), db: Session = Depends(get_db)):
    """Toglie un nome dal suo gruppo (separa di nuovo)."""
    key = normalize_text(name)
    groups = [[n for n in g if n != key] for g in _load_groups(db)]
    return _save_groups(db, groups)


@router.get("/invoice-destinations")
def invoice_destinations(limit: int = Query(250, ge=1, le=1000), db: Session = Depends(get_db)):
    items = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.supplier), selectinload(Invoice.meta).selectinload(InvoiceMeta.hotel))
        .order_by(Invoice.data.desc(), Invoice.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": inv.id,
            "number": inv.numero,
            "date": inv.data.isoformat(),
            "supplier": inv.supplier.ragione_sociale,
            "total": float(inv.totale or 0),
            "destination": inv.meta.hotel.code if inv.meta and inv.meta.hotel else None,
            "destination_name": inv.meta.hotel.name if inv.meta and inv.meta.hotel else "Generale / Apice",
        }
        for inv in items
    ]


@router.put("/invoice-destinations/{invoice_id}")
def set_invoice_destination(invoice_id: int, payload: dict, db: Session = Depends(get_db)):
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.meta)).where(Invoice.id == invoice_id))
    if not invoice:
        raise HTTPException(404, "Fattura non trovata")
    if not invoice.meta:
        from ..eye_services import ensure_invoice_metadata
        ensure_invoice_metadata(db, invoice, None)
        db.flush()
    code = str(payload.get("hotel_code") or "").strip().lower()
    if not code or code == "general":
        invoice.meta.hotel_id = None
        db.commit()
        return {"ok": True, "destination": None, "destination_name": "Generale / Apice"}
    hotel = db.scalar(select(Hotel).where(Hotel.code == code, Hotel.active.is_(True)))
    if not hotel:
        raise HTTPException(404, "Destinazione hotel non trovata")
    invoice.meta.hotel_id = hotel.id
    db.commit()
    return {"ok": True, "destination": hotel.code, "destination_name": hotel.name}
