from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Hotel, Invoice, InvoiceMeta
from ..report_service import historical_product_report

router = APIRouter(prefix="/api/eye", tags=["Eye Supremo reports"])


@router.get("/reports/history-product")
def history_product(q: str = Query(min_length=1, max_length=180), db: Session = Depends(get_db)):
    return historical_product_report(db, q)


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
