import json
import re
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .eye_services import invoice_search, invoice_search_summary, review_rankings
from .models import Hotel, Review, Room


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
        async with httpx.AsyncClient(timeout=2) as client:
            status = await client.get(f"{settings.ollama_url}/api/tags")
            status.raise_for_status()
        prompt = (
            "Sei Eye Supremo, assistente gestionale hotel. Rispondi in italiano usando ESCLUSIVAMENTE il JSON fornito. "
            "Non inventare importi, camere, ranking o recensioni. Per domande di spesa usa invoice_summary.row_total, "
            "che somma solo le righe pertinenti, non il totale delle fatture. Indica sempre le fonti utili.\n"
            f"DOMANDA: {question}\nCONTESTO:\n{json.dumps(context, ensure_ascii=False, default=str)}"
        )
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(f"{settings.ollama_url}/api/generate", json={
                "model": settings.chat_model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0.1, "num_predict": 550},
            })
            res.raise_for_status()
            answer = res.json().get("response", "")
        return {"mode": "ollama", "answer": answer, "context": context}
    except Exception:
        summary = context["invoice_summary"]
        if invoice_records:
            answer = f"Ho trovato {summary['rows']} righe pertinenti in {summary['invoices']} fatture, per € {summary['row_total']:.2f} sulle sole righe trovate."
        elif review_records:
            answer = f"Ho trovato {len(review_records)} recensioni pertinenti. Ollama non è disponibile: mostro i dati locali senza generazione IA."
        else:
            answer = "Non ho trovato dati pertinenti nell'archivio locale."
        return {"mode": "deterministic", "answer": answer, "context": context}
