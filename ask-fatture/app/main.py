from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ask import ask, ollama_ready
from .config import settings
from .db import db, init_db
from .import_xml import parse_fatturapa

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Ask Fatture", version="0.1.0", lifespan=lifespan)


class AskIn(BaseModel):
    question: str


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "model": settings.model}


@app.get("/api/status")
async def status():
    ollama = await ollama_ready()
    with db() as conn:
        invoices = conn.execute("SELECT COUNT(*) AS c FROM invoices").fetchone()["c"]
        lines = conn.execute("SELECT COUNT(*) AS c FROM lines").fetchone()["c"]
    return {
        "app": settings.app_name,
        "model": settings.model,
        "ollama": ollama,
        "invoices": invoices,
        "lines": lines,
        "data_dir": str(settings.data_dir),
    }


@app.post("/api/import")
async def import_invoice(file: UploadFile = File(...)):
    name = file.filename or "fattura.xml"
    if not name.lower().endswith(".xml"):
        raise HTTPException(415, "Per ora solo XML FatturaPA")
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "File troppo grande")
    dest = settings.data_dir / "uploads" / name
    dest.write_bytes(raw)
    try:
        parsed = parse_fatturapa(dest)
    except Exception as exc:
        raise HTTPException(422, f"XML non valido: {exc}") from exc
    if not parsed["rows"]:
        raise HTTPException(422, "Nessuna riga trovata nel XML")
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO invoices(numero, data, fornitore, totale, file_name) VALUES (?,?,?,?,?)",
            (parsed["numero"], parsed["data"], parsed["fornitore"], parsed["totale"], name),
        )
        invoice_id = cur.lastrowid
        for row in parsed["rows"]:
            conn.execute(
                """INSERT INTO lines(invoice_id, descrizione, quantita, unita, prezzo_unitario, totale_riga)
                   VALUES (?,?,?,?,?,?)""",
                (
                    invoice_id,
                    row["descrizione"],
                    row["quantita"],
                    row["unita"],
                    row["prezzo_unitario"],
                    row["totale_riga"],
                ),
            )
    return {
        "ok": True,
        "invoice_id": invoice_id,
        "fornitore": parsed["fornitore"],
        "numero": parsed["numero"],
        "rows": len(parsed["rows"]),
    }


@app.get("/api/invoices")
def list_invoices():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, numero, data, fornitore, totale, created_at FROM invoices ORDER BY id DESC LIMIT 50"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/ask")
async def ask_endpoint(payload: AskIn):
    q = (payload.question or "").strip()
    if not q:
        raise HTTPException(422, "Domanda vuota")
    return await ask(q)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/assets", StaticFiles(directory=STATIC), name="assets")
