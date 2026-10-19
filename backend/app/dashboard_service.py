"""Dashboard deterministica su archivio locale e cache, senza richieste di rete."""
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import AppSetting, CentralInvoiceCache, Invoice, Product, Supplier


def _identity(supplier, number, issued, total):
    return (str(supplier).strip().casefold(), str(number).strip().casefold(), issued, Decimal(total or 0))


def dashboard_snapshot(db: Session) -> dict:
    # Legge solo i metadati necessari. I payload con tutte le righe vengono
    # caricati soltanto per le fatture recenti effettivamente visualizzate.
    local = db.execute(select(Invoice.id, Invoice.hash_file, Invoice.numero, Invoice.data,
                              Invoice.totale, Supplier.ragione_sociale)
                       .join(Supplier, Supplier.id == Invoice.supplier_id)).all()
    hashes = {row.hash_file for row in local if row.hash_file}
    identities = {_identity(row.ragione_sociale, row.numero, row.data, row.totale) for row in local}
    rows = [{"id": row.id, "date": row.data, "number": row.numero, "total": row.totale,
             "supplier": row.ragione_sociale, "local": True} for row in local]
    for row in db.execute(select(CentralInvoiceCache.source_hash, CentralInvoiceCache.invoice_number,
                                 CentralInvoiceCache.invoice_date, CentralInvoiceCache.total,
                                 CentralInvoiceCache.supplier_name)):
        key = _identity(row.supplier_name, row.invoice_number, row.invoice_date, row.total)
        if row.source_hash in hashes or key in identities:
            continue
        identities.add(key)
        rows.append({"id": row.source_hash, "date": row.invoice_date, "number": row.invoice_number,
                     "total": row.total, "supplier": row.supplier_name, "local": False})
    positive = sorted((r for r in rows if r['total'] >= 0), key=lambda r: (r['date'], str(r['id'])), reverse=True)
    credits = [r for r in rows if r['total'] < 0]
    monthly = defaultdict(Decimal)
    annual = defaultdict(lambda: {"total": Decimal(0), "invoices": 0})
    for row in positive:
        monthly[row['date'].strftime('%Y-%m')] += row['total']
        year = annual[str(row['date'].year)]
        year['total'] += row['total']; year['invoices'] += 1
    recent = []
    recent_local_ids = [r['id'] for r in positive[:6] if r['local']]
    local_details = {i.id: i for i in db.scalars(select(Invoice).where(Invoice.id.in_(recent_local_ids))
                     .options(selectinload(Invoice.supplier), selectinload(Invoice.rows)))}
    for row in positive[:6]:
        if row['local']:
            inv = local_details[row['id']]
            recent.append({"id": inv.id, "numero": inv.numero, "data": inv.data.isoformat(),
                           "imponibile": float(inv.imponibile), "iva": float(inv.iva), "totale": float(inv.totale),
                           "valuta": inv.valuta, "stato_importazione": inv.stato_importazione,
                           "file_originale": inv.file_originale, "supplier": {"id": inv.supplier_id,
                           "ragione_sociale": inv.supplier.ragione_sociale}, "row_count": len(inv.rows)})
        else:
            record = db.get(CentralInvoiceCache, row['id'])
            try:
                payload = json.loads(record.payload_json or '{}')
                if not isinstance(payload, dict): payload = {}
            except (TypeError, ValueError):
                payload = {}
            recent.append({"id": row['id'], "numero": row['number'], "data": row['date'].isoformat(),
                           "imponibile": float(payload.get('taxable') or 0), "iva": float(payload.get('vat') or 0),
                           "totale": float(row['total']), "valuta": payload.get('currency') or 'EUR',
                           "stato_importazione": 'Cache centrale', "file_originale": payload.get('source_filename') or '',
                           "supplier": {"id": row['supplier'], "ragione_sociale": row['supplier']},
                           "row_count": len(payload.get('rows') or [])})
    months = sorted(monthly)
    # Il catalogo disponibile offline è conteggiato dal database, senza un RPC
    # che potrebbe bloccare la dashboard per il timeout di rete.
    products = db.scalar(select(func.count(Product.id))) or 0
    cached_count = db.get(AppSetting, 'dashboard_product_count')
    if cached_count:
        try: products = max(products, int(cached_count.value))
        except (TypeError, ValueError): pass
    return {"kpis": {"invoices": len(positive), "total_spent": float(sum((r['total'] for r in positive), Decimal(0))),
                     "month_spent": float(monthly.get(date.today().strftime('%Y-%m'), 0)),
                     "suppliers": len({r['supplier'].strip().casefold() for r in positive}), "products": products},
            "period": {"from": positive[-1]['date'].isoformat() if positive else None,
                       "to": positive[0]['date'].isoformat() if positive else None,
                       "latest_month": months[-1] if months else None,
                       "latest_month_spent": float(monthly[months[-1]]) if months else 0,
                       "credit_documents": len(credits), "credit_total": float(sum((r['total'] for r in credits), Decimal(0)))},
            "annual": [{"year": year, "total": float(v['total']), "invoices": v['invoices']} for year,v in sorted(annual.items())],
            "monthly": [{"month": month, "total": float(monthly[month])} for month in months[-24:]],
            "recent": recent}
