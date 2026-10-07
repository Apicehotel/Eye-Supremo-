import json
import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from .agent_orchestrator import ASK_NUM_CTX, ASK_NUM_PREDICT, ASK_REVIEW_LIMIT, ASK_ROW_LIMIT, _compact_for_llm
from .eye_services import invoice_search_summary, review_rankings
from .model_layers import generate_with_layers, resolve_ai_runtime
from .review_cache import cached_review_search
from .search_index import invoice_search
from .models import Hotel, Review, Room

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["answer", "facts", "confidence"],
}


async def eye_ai_answer(db: Session, question: str, role_name: str = "developer", hotel_id: int | None = None) -> dict:
    invoice_records = invoice_search(db, question, role_name=role_name, limit=ASK_ROW_LIMIT)
    review_stmt = select(Review, Hotel, Room).join(Hotel, Review.hotel_id == Hotel.id).outerjoin(Room, Review.room_id == Room.id)
    if hotel_id:
        review_stmt = review_stmt.where(Review.hotel_id == hotel_id)
    tokens = [x for x in re.findall(r"\w+", question.lower()) if len(x) >= 4]
    if tokens:
        review_stmt = review_stmt.where(Review.text.ilike(f"%{tokens[-1]}%"))
    reviews = db.execute(review_stmt.order_by(Review.date.desc()).limit(ASK_REVIEW_LIMIT)).all()
    review_records = [{
        "review_id": r.id, "hotel": h.name, "room": room.code if room else None,
        "date": r.date.isoformat(), "rating": float(r.rating) if r.rating is not None else None,
        "text": r.text[:280], "source": r.source, "source_origin": "local",
    } for r, h, room in reviews]
    if len(review_records) < ASK_REVIEW_LIMIT:
        seen = {str(r.sync_uuid) for r, _, _ in reviews if getattr(r, "sync_uuid", None)}
        for item in cached_review_search(
            db,
            question,
            hotel_id=hotel_id,
            limit=ASK_REVIEW_LIMIT - len(review_records),
            exclude_sync_uuids=seen,
        ):
            review_records.append({
                "review_id": item["review_id"],
                "hotel": item.get("hotel"),
                "room": item.get("room"),
                "date": item.get("date"),
                "rating": item.get("rating"),
                "text": item.get("text"),
                "source": item.get("source"),
                "source_origin": "sqlite-cache",
            })
    rankings = review_rankings(db, hotel_id=hotel_id, limit=5)
    context = {
        "invoice_summary": invoice_search_summary(invoice_records),
        "invoice_rows": invoice_records,
        "reviews": review_records,
        "rankings": rankings,
    }
    try:
        runtime = resolve_ai_runtime(db)
        compact = _compact_for_llm(context)
        prompt = (
            "Sei Eye Supremo, assistente gestionale hotel. Usa solo il JSON. "
            "Italiano, max 3 frasi. Non inventare dati. Per spese usa invoice_summary.row_total.\n"
            f"DOMANDA: {question}\nCONTESTO:\n{json.dumps(compact, ensure_ascii=False, default=str)}"
        )
        structured = await generate_with_layers(
            prompt=prompt,
            runtime=runtime,
            response_format=ANSWER_SCHEMA,
            temperature=0.0,
            num_predict=ASK_NUM_PREDICT,
            num_ctx=ASK_NUM_CTX,
            request_timeout=35.0,
            escalate_on_low_confidence=False,
        )
        answer = str(structured.get("answer", "")).strip()
        if not answer:
            raise ValueError("Risposta strutturata vuota")
        return {
            "mode": "ollama",
            "answer": answer,
            "facts": structured.get("facts", []),
            "confidence": structured.get("confidence", "medium"),
            "context": compact,
            "ai_layer": structured.get("_layer"),
            "ai_model": structured.get("_model"),
            "ai_policy": runtime.policy,
        }
    except Exception:
        summary = context["invoice_summary"]
        if invoice_records:
            answer = f"Ho trovato {summary['rows']} righe pertinenti in {summary['invoices']} fatture, per € {summary['row_total']:.2f} sulle sole righe trovate."
        elif review_records:
            answer = f"Ho trovato {len(review_records)} recensioni pertinenti. Ollama non è disponibile: mostro i dati locali senza generazione IA."
        else:
            answer = "Non ho trovato dati pertinenti nell'archivio locale."
        return {
            "mode": "deterministic",
            "answer": answer,
            "facts": [],
            "confidence": "high",
            "context": context,
            "ai_layer": "deterministic",
            "ai_model": None,
        }
