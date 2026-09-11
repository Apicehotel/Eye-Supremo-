from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .eye_services import invoice_search_summary, review_rankings
from .models import Hotel, Review, Room
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

PRODUCT_HINTS = ("prodotto", "prezzo", "costa", "fornitore", "vende", "meglio", "storico", "media", "minimo", "massimo")
REVIEW_HINTS = ("recensione", "camera", "staff", "pulizia", "colazione", "ristorante", "servizio", "ranking")
CLASSIFY_HINTS = ("categoria", "classifica", "food", "beverage", "non food", "che prodotto", "tipologia")


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
    ordered = []
    for name in agents:
        if name not in ordered:
            ordered.append(name)
    ordered.extend(["verifier", "answer"])
    return ordered


def _review_context(db: Session, question: str, hotel_id: int | None = None) -> dict[str, Any]:
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


def _product_context(db: Session, question: str, role_name: str) -> dict[str, Any]:
    rows = invoice_search(db, question, role_name=role_name, limit=40)
    report = None
    try:
        report = historical_product_report(db, question)
    except Exception:
        report = None
    return {
        "invoice_rows": rows,
        "invoice_summary": invoice_search_summary(rows),
        "historical_product": report,
    }


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


async def _qwen_structured(question: str, context: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "Sei l'agente risposta di Eye Supremo. Usa solo il contesto fornito. "
        "Non inventare dati. Mantieni separati prodotti con significato diverso anche se simili nel testo. "
        "Per prezzi usa solo unità confrontabili. Rispondi in italiano, breve e chiaro.\n"
        f"DOMANDA: {question}\nCONTESTO: {json.dumps(context, ensure_ascii=False, default=str)}"
    )
    async with httpx.AsyncClient(timeout=2) as client:
        status = await client.get(f"{settings.ollama_url}/api/tags")
        status.raise_for_status()
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(f"{settings.ollama_url}/api/generate", json={
            "model": settings.chat_model,
            "prompt": prompt,
            "stream": False,
            "format": ANSWER_SCHEMA,
            "options": {"temperature": 0.0, "num_predict": 650},
        })
        res.raise_for_status()
        return json.loads(res.json().get("response", "{}"))


async def run_orchestrated_query(db: Session, question: str, role_name: str = "developer", hotel_id: int | None = None) -> dict[str, Any]:
    plan = classify_intent(question)
    context: dict[str, Any] = {}

    workers: list[Awaitable[tuple[str, dict[str, Any]]]] = []

    async def product_worker():
        return "product", await asyncio.to_thread(_product_context, db, question, role_name)

    async def review_worker():
        return "review", await asyncio.to_thread(_review_context, db, question, hotel_id)

    if any(a in plan for a in ("products", "prices", "invoices", "classifier")):
        workers.append(product_worker())
    if "reviews" in plan:
        workers.append(review_worker())

    if workers:
        for key, payload in await asyncio.gather(*workers):
            context.update(payload)

    verification = _verify(context)
    context["verification"] = verification

    try:
        structured = await _qwen_structured(question, context)
        answer = str(structured.get("answer", "")).strip()
        if not answer:
            raise ValueError("Risposta vuota")
        mode = "orchestrated-ollama"
        confidence = structured.get("confidence", "medium")
        facts = structured.get("facts", [])
    except Exception:
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

    return {
        "mode": mode,
        "plan": plan,
        "agents": [{"name": name, "purpose": AGENTS[name].purpose} for name in plan],
        "answer": answer,
        "facts": facts,
        "confidence": confidence,
        "verification": verification,
        "context": context,
    }
