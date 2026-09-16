from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Invoice, InvoiceRow, Product, WarehouseMovement, WarehouseStockSetting
from ..services import audit

router = APIRouter(prefix="/api/warehouse", tags=["warehouse"])


def _signed_quantity(movement: WarehouseMovement) -> Decimal:
    if movement.movement_type == "out":
        return -movement.quantity
    return movement.quantity


def _serialize_movement(movement: WarehouseMovement, product: Product | None = None):
    return {
        "id": movement.id,
        "product_id": movement.product_id,
        "product": product.nome_canonico if product else None,
        "invoice_row_id": movement.invoice_row_id,
        "movement_type": movement.movement_type,
        "quantity": float(movement.quantity),
        "signed_quantity": float(_signed_quantity(movement)),
        "unit": movement.unit,
        "unit_cost": float(movement.unit_cost) if movement.unit_cost is not None else None,
        "note": movement.note,
        "created_at": movement.created_at.isoformat(),
    }


@router.get("/summary")
def warehouse_summary(db: Session = Depends(get_db)):
    products = db.scalars(select(Product).order_by(Product.nome_canonico)).all()
    settings = {x.product_id: x for x in db.scalars(select(WarehouseStockSetting)).all()}
    result = []
    for product in products:
        movements = db.scalars(select(WarehouseMovement).where(WarehouseMovement.product_id == product.id).order_by(WarehouseMovement.created_at)).all()
        stock = sum((_signed_quantity(x) for x in movements), Decimal("0"))
        setting = settings.get(product.id)
        minimum = setting.min_quantity if setting else Decimal("0")
        latest_cost = next((m.unit_cost for m in reversed(movements) if m.unit_cost is not None), None)
        result.append({
            "product_id": product.id,
            "product": product.nome_canonico,
            "category": product.categoria,
            "unit": product.unita_base or (movements[-1].unit if movements else "pz"),
            "stock": float(stock),
            "min_quantity": float(minimum),
            "low_stock": bool(setting and setting.enabled and stock <= minimum),
            "tracking_enabled": bool(setting.enabled) if setting else False,
            "movement_count": len(movements),
            "latest_unit_cost": float(latest_cost) if latest_cost is not None else None,
        })
    return result


@router.get("/movements")
def warehouse_movements(product_id: int | None = None, limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    stmt = select(WarehouseMovement).order_by(WarehouseMovement.created_at.desc()).limit(limit)
    if product_id:
        stmt = select(WarehouseMovement).where(WarehouseMovement.product_id == product_id).order_by(WarehouseMovement.created_at.desc()).limit(limit)
    movements = db.scalars(stmt).all()
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_([m.product_id for m in movements]))).all()} if movements else {}
    return [_serialize_movement(m, products.get(m.product_id)) for m in movements]


@router.post("/movements")
def create_warehouse_movement(payload: dict, db: Session = Depends(get_db)):
    try:
        product_id = int(payload.get("product_id"))
        quantity = Decimal(str(payload.get("quantity", "0")))
    except Exception:
        raise HTTPException(422, "Prodotto o quantità non validi")
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Prodotto non trovato")
    movement_type = str(payload.get("movement_type", "in")).lower()
    if movement_type not in {"in", "out", "adjustment"}:
        raise HTTPException(422, "Tipo movimento non valido")
    if movement_type in {"in", "out"} and quantity <= 0:
        raise HTTPException(422, "La quantità deve essere maggiore di zero")
    if movement_type == "adjustment" and quantity == 0:
        raise HTTPException(422, "La rettifica non può essere zero")
    unit_cost = payload.get("unit_cost")
    movement = WarehouseMovement(
        product_id=product.id,
        movement_type=movement_type,
        quantity=quantity,
        unit=str(payload.get("unit") or product.unita_base or "pz")[:20],
        unit_cost=Decimal(str(unit_cost)) if unit_cost not in {None, ""} else None,
        note=str(payload.get("note") or "")[:500] or None,
    )
    db.add(movement)
    audit(db, "warehouse.movement", f"Movimento {movement_type} {quantity} {movement.unit} per {product.nome_canonico}", entity_type="product", entity_id=product.id)
    db.commit(); db.refresh(movement)
    return _serialize_movement(movement, product)


@router.post("/from-invoice/{invoice_id}")
def warehouse_from_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Fattura non trovata")
    rows = db.scalars(select(InvoiceRow).where(InvoiceRow.invoice_id == invoice_id)).all()
    created = 0; skipped = 0
    for row in rows:
        if not row.product_id:
            skipped += 1; continue
        exists = db.scalar(select(WarehouseMovement).where(WarehouseMovement.invoice_row_id == row.id))
        if exists:
            skipped += 1; continue
        movement = WarehouseMovement(
            product_id=row.product_id,
            invoice_row_id=row.id,
            movement_type="in",
            quantity=row.quantita,
            unit=row.unita_normalizzata or row.unita_originale or "pz",
            unit_cost=row.prezzo_normalizzato or row.prezzo_unitario,
            note=f"Carico automatico da fattura {invoice.numero}",
        )
        db.add(movement); created += 1
    audit(db, "warehouse.invoice_loaded", f"Fattura {invoice.numero}: {created} carichi creati, {skipped} righe saltate", entity_type="invoice", entity_id=invoice.id)
    db.commit()
    return {"ok": True, "created": created, "skipped": skipped}


@router.put("/products/{product_id}/threshold")
def set_threshold(product_id: int, payload: dict, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Prodotto non trovato")
    try:
        minimum = Decimal(str(payload.get("min_quantity", "0")))
    except Exception:
        raise HTTPException(422, "Soglia non valida")
    if minimum < 0:
        raise HTTPException(422, "La soglia non può essere negativa")
    setting = db.get(WarehouseStockSetting, product_id)
    if not setting:
        setting = WarehouseStockSetting(product_id=product_id)
        db.add(setting)
    setting.min_quantity = minimum
    setting.enabled = bool(payload.get("enabled", True))
    audit(db, "warehouse.threshold", f"Soglia {product.nome_canonico}: {minimum}", entity_type="product", entity_id=product.id)
    db.commit()
    return {"ok": True, "product_id": product_id, "min_quantity": float(minimum), "enabled": setting.enabled}
