from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .central_service import central_invoice_search
from .eye_services import invoice_search_summary, review_rankings
from .model_layers import AiRuntime, generate_with_layers, resolve_ai_runtime
from .models import CentralInvoiceCache, Hotel, Invoice, Review, Room, Supplier
from .report_service import historical_product_report
from .search_index import invoice_search


@dataclass(frozen=True)
class AgentSpec:
    name: str
    purpose: str
    tools: tuple[str, ...]


AGENTS: dict[str, AgentSpec] = {
    "router": AgentSpec("router", "Capisce il lavoro e sceglie gli specialisti", ("classify_intent",)),
    "products": AgentSpec("products", "Trova prodotti, alias e corrispondenze pulite", ("invoice_search", "historical_product_report")),
    "classifier": AgentSpec("classifier", "Classifica Food & Beverage / Non Food e sottocategorie", ("structured_qwen",)),
    "invoices": AgentSpec("invoices", "Interpreta dati fattura e fornitori", ("invoice_search",)),
    "prices": AgentSpec("prices", "Calcola storico, medie, minimi e variazioni", ("historical_product_report",)),
    "reviews": AgentSpec("reviews", "Analizza recensioni, camere, servizi e ranking", ("reviews", "rankings")),
    "verifier": AgentSpec("verifier", "Controlla coerenza, unità e falsi positivi", ("deterministic_checks",)),
    "answer": AgentSpec("answer", "Produce una risposta breve e verificabile", ("structured_qwen",)),
}

# Usiamo radici lessicali, non parole intere, così singolare/plurale e piccole
# variazioni italiane non mandano la domanda allo specialista sbagliato.
PRODUCT_HINTS = ("prodott", "prezz", "cost", "fornitor", "vend", "meglio", "storic", "medi", "minim", "massim")
REVIEW_HINTS = ("recension", "camer", "staff", "pulizi", "colazion", "ristor", "servizi", "ranking")
CLASSIFY_HINTS = ("categor", "classific", "food", "beverage", "non food", "tipologi")


def _asks_for_max_invoice(question: str) -> bool:
    q = question.lower()
    return "fattur" in q and any(
        phrase in q
        for phrase in (
            "totale più alto",
            "totale piu alto",
            "fattura più alta",
            "fattura piu alta",
            "importo massimo",
            "importo più alto",
            "importo piu alto",
            "più costosa",
            "piu costosa",
        )
    )


def _max_invoice_context(db: Session) -> dict[str, Any] | None:
    """Return the highest positive invoice across local and central archives."""
    candidates: list[dict[str, Any]] = []
    local = db.execute(
        select(Invoice, Supplier)
        .join(Supplier, Invoice.supplier_id == Supplier.id)
        .where(Invoice.totale >= 0)
        .order_by(desc(Invoice.totale))
        .limit(1)
    ).first()
    if local:
        invoice, supplier = local
        candidates.append({
            "invoice_number": invoice.numero,
            "invoice_date": invoice.data.isoformat() if invoice.data else None,
            "supplier_name": supplier.ragione_sociale,
            "total": float(invoice.totale or 0),
            "taxable": float(invoice.imponibile or 0),
            "vat": float(invoice.iva or 0),
            "source": "local",
        })

    central = db.scalar(
        select(CentralInvoiceCache)
        .where(CentralInvoiceCache.total >= 0)
        .order_by(desc(CentralInvoiceCache.total))
        .limit(1)
    )
    if central:
        try:
            payload = json.loads(central.payload_json or "{}")
        except (TypeError, ValueError):
            payload = {}
        candidates.append({
            "invoice_number": central.invoice_number,
            "invoice_date": central.invoice_date.isoformat() if central.invoice_date else None,
            "supplier_name": central.supplier_name,
            "total": float(central.total or 0),
            "taxable": float(payload.get("taxable") or 0),
            "vat": float(payload.get("vat") or 0),
            "source": "central-cache",
            "source_filename": payload.get("source_filename"),
            "source_hash": central.source_hash,
        })
    return max(candidates, key=lambda item: item["total"]) if candidates else None


def classify_intent(question: str) -> list[str]:
    q = question.lower()
    agents: list[str] = []
    if any(x in q for x in REVIEW_HINTS):
        agents.append("reviews")
    if any(x in q for x in PRODUCT_HINTS):
        agents.extend(["products", "prices"])
    if any(x in q for x in CLASSIFY_HINTS):
        agents.append("classifier")
    if not agents:
        agents.append("products")
    ordered: list[str] = []
    for name in agents:
        if name not in ordered:
            ordered.append(name)
    ordered.extend(["verifier", "answer"])
    return ordered


def _review_context(question: str, hotel_id: int | None = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        stmt = select(Review, Hotel, Room).join(Hotel, Review.hotel_id == Hotel.id).outerjoin(Room, Review.room_id == Room.id)
        if hotel_id:
            stmt = stmt.where(Review.hotel_id == hotel_id)
        tokens = [x for x in re.findall(r"\w+", question.lower()) if len(x) >= 4]
        if tokens:
            stmt = stmt.where(Review.text.ilike(f"%{tokens[-1]}%"))
        rows = db.execute(stmt.order_by(Review.date.desc()).limit(30)).all()
        return {
            "reviews": [{
                "review_id": r.id,
                "hotel": h.name,
                "room": room.code if room else None,
                "date": r.date.isoformat(),
                "rating": float(r.rating) if r.rating is not None else None,
                "text": r.text[:1200],
                "source": r.source,
            } for r, h, room in rows],
            "rankings": review_rankings(db, hotel_id=hotel_id, limit=5),
        }
    finally:
        db.close()


async def _product_context(question: str, role_name: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        max_invoice = _max_invoice_context(db) if _asks_for_max_invoice(question) else None
        rows = invoice_search(db, question, role_name=role_name, limit=40)
        # Keep the bakery product family separate from similarly spelled
        # technical items such as bombole/bombole per pulizia.
        lowered_question = question.lower()
        if "bombolon" in lowered_question or "bobolon" in lowered_question:
            rows = [row for row in rows if any(token in str(row.get("description") or "").lower() for token in ("bombolin", "bombolon"))]
        # Le fatture centrali possono essere sincronizzate localmente per testata
        # senza caricare subito tutte le righe. In quel caso l'agente usa la
        # ricerca deterministica centrale, mantenendo Qwen fuori dal database.
        if not rows:
            words = [x for x in re.findall(r"[a-zàèéìòù0-9]+", question.lower())
                     if len(x) >= 5 and x not in {"quanto", "quale", "quali", "vende", "meglio", "fammi", "mostra", "classifica"}]
            candidates = []
            if words:
                term = words[-1]
                candidates.append(term)
                if term.endswith(("i", "e")) and len(term) > 5:
                    candidates.append(term[:-1])
            central = {"items": [], "count": 0}
            for term in candidates or [question]:
                central = await central_invoice_search(term, limit=40)
                if central.get("items"):
                    break
            rows = [{
                "row_id": item.get("id"),
                "invoice_id": item.get("source_hash") or item.get("id"),
                "invoice": item.get("invoice_number"),
                "date": item.get("invoice_date"),
                "supplier": item.get("supplier_name"),
                "description": item.get("original_description") or item.get("normalized_description"),
                "quantity": float(item.get("quantity") or 0),
                "unit_price": float(item.get("unit_price") or 0),
                "row_total": float(item.get("line_total") or 0),
                "normalized_price": None,
                "unit": None,
                "analysis_status": item.get("analysis_status") or "product",
            } for item in central.get("items", [])]
        if "bombolon" in lowered_question or "bobolon" in lowered_question:
            rows = [row for row in rows if any(token in str(row.get("description") or "").lower() for token in ("bombolin", "bombolon"))]
        try:
            report = historical_product_report(db, question)
        except Exception:
            report = None
        return {
            "invoice_rows": rows,
            "invoice_summary": invoice_search_summary(rows),
            "historical_product": report,
            **({"max_invoice": max_invoice} if max_invoice else {}),
        }
    finally:
        db.close()


def _verify(context: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    hist = context.get("historical_product") or {}
    units = {str(x.get("unit")) for x in hist.get("timeline", []) if x.get("unit")}
    if len(units) > 1:
        warnings.append("Sono presenti unità diverse: confrontare solo prezzi normalizzati compatibili.")
    rows = context.get("invoice_rows") or []
    if rows:
        terms = {str(r.get("description", "")).lower() for r in rows}
        if any("bombola" in t for t in terms) and any("bombolone" in t for t in terms):
            warnings.append("Rilevata possibile collisione bombola/bombolone: risultati da tenere separati.")
    return {"ok": not warnings, "warnings": warnings}


ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["answer", "facts", "confidence"],
}


async def _qwen_structured(question: str, context: dict[str, Any], runtime: AiRuntime) -> dict[str, Any]:
    prompt = (
        "Sei l'agente risposta di Eye Supremo. Usa solo il contesto fornito. "
        "Non inventare dati. Mantieni separati prodotti con significato diverso anche se simili nel testo. "
        "Per prezzi usa solo unità confrontabili. Rispondi in italiano, breve e chiaro.\n"
        f"DOMANDA: {question}\nCONTESTO: {json.dumps(context, ensure_ascii=False, default=str)}"
    )
    return await generate_with_layers(
        prompt=prompt,
        runtime=runtime,
        response_format=ANSWER_SCHEMA,
        temperature=0.0,
        num_predict=650,
    )


async def run_orchestrated_query(db: Session, question: str, role_name: str = "developer", hotel_id: int | None = None) -> dict[str, Any]:
    # Runtime IA letto subito: i worker paralleli aprono sessioni SQLite separate.
    runtime = resolve_ai_runtime(db)
    del db
    plan = classify_intent(question)
    context: dict[str, Any] = {}
    workers: list[Awaitable[tuple[str, dict[str, Any]]]] = []
    ai_layer: str | None = None
    ai_model: str | None = None

    async def product_worker():
        return "product", await _product_context(question, role_name)

    async def review_worker():
        return "review", await asyncio.to_thread(_review_context, question, hotel_id)

    if any(a in plan for a in ("products", "prices", "invoices", "classifier")):
        workers.append(product_worker())
    if "reviews" in plan:
        workers.append(review_worker())

    if workers:
        for _, payload in await asyncio.gather(*workers):
            context.update(payload)

    verification = _verify(context)
    context["verification"] = verification

    try:
        structured = await _qwen_structured(question, context, runtime)
        answer = str(structured.get("answer", "")).strip()
        if not answer:
            raise ValueError("Risposta vuota")
        mode = "orchestrated-ollama"
        confidence = structured.get("confidence", "medium")
        facts = structured.get("facts", [])
        ai_layer = structured.get("_layer")
        ai_model = structured.get("_model")
    except Exception:
        max_invoice = context.get("max_invoice")
        if max_invoice:
            answer = (
                f"La fattura con il totale più alto è la n. {max_invoice['invoice_number']} "
                f"di {max_invoice['supplier_name']}, del {max_invoice['invoice_date']}, "
                f"per € {max_invoice['total']:.2f}."
            )
            mode = "orchestrated-deterministic"
            confidence = "high"
            facts = []
            return {
                "mode": mode,
                "plan": plan,
                "agents": [{"name": name, "purpose": AGENTS[name].purpose} for name in plan],
                "answer": answer,
                "facts": facts,
                "confidence": confidence,
                "verification": verification,
                "context": context,
                "ai_layer": "deterministic",
                "ai_model": None,
                "ai_policy": runtime.policy,
            }
        summary = context.get("invoice_summary") or {"rows": 0, "invoices": 0, "row_total": 0}
        if summary.get("rows"):
            answer = f"Ho trovato {summary['rows']} righe pertinenti in {summary['invoices']} fatture, per € {summary['row_total']:.2f}."
        elif context.get("reviews"):
            answer = f"Ho trovato {len(context['reviews'])} recensioni pertinenti nell'archivio locale."
        else:
            answer = "Non ho trovato dati pertinenti nell'archivio locale."
        mode = "orchestrated-deterministic"
        confidence = "high" if verification["ok"] else "medium"
        facts = []
        ai_layer = "deterministic"
        ai_model = None

    return {
        "mode": mode,
        "plan": plan,
        "agents": [{"name": name, "purpose": AGENTS[name].purpose} for name in plan],
        "answer": answer,
        "facts": facts,
        "confidence": confidence,
        "verification": verification,
        "context": context,
        "ai_layer": ai_layer,
        "ai_model": ai_model,
        "ai_policy": runtime.policy,
    }
