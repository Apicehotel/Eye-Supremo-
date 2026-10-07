import json
import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from .eye_services import invoice_search_summary, review_rankings
from .model_layers import generate_with_layers, resolve_ai_runtime
from .search_index import invoice_search
from .models import Hotel, Review, Room

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["answer", "facts", "confidence"],
}


async def eye_ai_answer(db: Session, question: str, role_name: str = "developer", hotel_id: int | None = None) -> dict:
    invoice_records = invoice_search(db, question, role_name=role_name, limit=40)
    review_stmt = select(Review, Hotel, Room).join(Hotel, Review.hotel_id == Hotel.id).outerjoin(Room, Review.room_id == Room.id)
    if hotel_id:
        review_stmt = review_stmt.where(Review.hotel_id == hotel_id)
    tokens = [x for x in re.findall(r"\w+", question.lower()) if len(x) >= 4]
    if tokens:
        review_stmt = review_stmt.where(Review.text.ilike(f"%{tokens[-1]}%"))
    reviews = db.execute(review_stmt.order_by(Review.date.desc()).limit(30)).all()
    review_records = [{
        "review_id": r.id, "hotel": h.name, "room": room.code if room else None,
        "date": r.date.isoformat(), "rating": float(r.rating) if r.rating is not None else None,
        "text": r.text[:1200], "source": r.source,
    } for r, h, room in reviews]
    rankings = review_rankings(db, hotel_id=hotel_id, limit=5)
    context = {
        "invoice_summary": invoice_search_summary(invoice_records),
        "invoice_rows": invoice_records,
        "reviews": review_records,
        "rankings": rankings,
    }
    try:
        runtime = resolve_ai_runtime(db)
        prompt = (
            "Sei Eye Supremo, assistente gestionale hotel. Rispondi in italiano usando ESCLUSIVAMENTE il JSON fornito. "
            "Non inventare importi, camere, ranking, produttori, fornitori o recensioni. Per domande di spesa usa invoice_summary.row_total, "
            "che somma solo le righe pertinenti e non il totale delle fatture. Se il contesto non basta, dillo chiaramente. "
            "Nel campo facts inserisci solo fatti verificabili presenti nel contesto.\n"
            f"DOMANDA: {question}\nCONTESTO:\n{json.dumps(context, ensure_ascii=False, default=str)}"
        )
        structured = await generate_with_layers(
            prompt=prompt,
            runtime=runtime,
            response_format=ANSWER_SCHEMA,
            temperature=0.0,
            num_predict=650,
        )
        answer = str(structured.get("answer", "")).strip()
        if not answer:
            raise ValueError("Risposta strutturata vuota")
        return {
            "mode": "ollama",
            "answer": answer,
            "facts": structured.get("facts", []),
            "confidence": structured.get("confidence", "medium"),
            "context": context,
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
