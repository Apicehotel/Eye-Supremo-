from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ask import ask, ollama_ready
from .catalog import supplier_to_dict, upsert_product, upsert_supplier
from .config import settings
from .db import db, dump_sconti, init_db
from .import_xml import parse_fatturapa

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Ask Fatture", version="0.2.0", lifespan=lifespan)


class AskIn(BaseModel):
    question: str


class ScontoIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    percentuale: float | None = None
    note: str | None = None
    prodotto: str | None = None


class SupplierUpdate(BaseModel):
    ragione_sociale: str | None = None
    nome_commerciale: str | None = None
    partita_iva: str | None = None
    codice_fiscale: str | None = None
    indirizzo: str | None = None
    cap: str | None = None
    citta: str | None = None
    provincia: str | None = None
    nazione: str | None = None
    email: str | None = None
    telefono: str | None = None
    pec: str | None = None
    note: str | None = None
    sconti: list[ScontoIn] | None = None


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "model": settings.model}


@app.get("/api/status")
async def status():
    ollama = await ollama_ready()
    with db() as conn:
        invoices = conn.execute("SELECT COUNT(*) AS c FROM invoices").fetchone()["c"]
        lines = conn.execute("SELECT COUNT(*) AS c FROM lines").fetchone()["c"]
        suppliers = conn.execute("SELECT COUNT(*) AS c FROM suppliers").fetchone()["c"]
        products = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    return {
        "app": settings.app_name,
        "model": settings.model,
        "ollama": ollama,
        "invoices": invoices,
        "lines": lines,
        "suppliers": suppliers,
        "products": products,
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
        supplier_id = upsert_supplier(conn, parsed["supplier"])
        cur = conn.execute(
            """INSERT INTO invoices(supplier_id, numero, data, fornitore, totale, file_name)
               VALUES (?,?,?,?,?,?)""",
            (
                supplier_id,
                parsed["numero"],
                parsed["data"],
                parsed["fornitore"],
                parsed["totale"],
                name,
            ),
        )
        invoice_id = cur.lastrowid
        for row in parsed["rows"]:
            product_id = upsert_product(
                conn,
                row["descrizione"],
                row.get("descrizione_norm"),
                row.get("unita_normalizzata") or row.get("unita"),
            )
            conn.execute(
                """INSERT INTO lines(
                     invoice_id, product_id, descrizione, descrizione_norm, quantita, unita,
                     unita_normalizzata, prezzo_unitario, prezzo_normalizzato,
                     contenuto_base, totale_riga
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    invoice_id,
                    product_id,
                    row["descrizione"],
                    row.get("descrizione_norm"),
                    row["quantita"],
                    row["unita"],
                    row.get("unita_normalizzata"),
                    row["prezzo_unitario"],
                    row.get("prezzo_normalizzato"),
                    row.get("contenuto_base"),
                    row["totale_riga"],
                ),
            )
        supplier = conn.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()

    return {
        "ok": True,
        "invoice_id": invoice_id,
        "supplier_id": supplier_id,
        "supplier": supplier_to_dict(supplier) if supplier else parsed["supplier"],
        "fornitore": parsed["fornitore"],
        "numero": parsed["numero"],
        "rows": len(parsed["rows"]),
        "skipped": len(parsed.get("skipped") or []),
        "skipped_details": (parsed.get("skipped") or [])[:20],
    }


@app.get("/api/invoices")
def list_invoices():
    with db() as conn:
        rows = conn.execute(
            """SELECT i.id, i.numero, i.data, i.fornitore, i.totale, i.created_at, i.supplier_id,
                      s.partita_iva
               FROM invoices i
               LEFT JOIN suppliers s ON s.id = i.supplier_id
               ORDER BY i.id DESC LIMIT 50"""
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/suppliers")
def list_suppliers(q: str = ""):
    with db() as conn:
        if q.strip():
            like = f"%{q.strip()}%"
            rows = conn.execute(
                """SELECT * FROM suppliers
                   WHERE ragione_sociale LIKE ? OR ifnull(partita_iva,'') LIKE ?
                      OR ifnull(nome_commerciale,'') LIKE ?
                   ORDER BY ragione_sociale LIMIT 100""",
                (like, like, like),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM suppliers ORDER BY ragione_sociale LIMIT 100").fetchall()
    return [supplier_to_dict(r) for r in rows]


@app.get("/api/suppliers/{supplier_id}")
def get_supplier(supplier_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Fornitore non trovato")
        products = conn.execute(
            """SELECT p.id, p.nome, p.unita_base,
                      COUNT(l.id) AS righe,
                      MIN(l.prezzo_normalizzato) AS prezzo_min,
                      MAX(l.prezzo_normalizzato) AS prezzo_max
               FROM lines l
               JOIN invoices i ON i.id = l.invoice_id
               JOIN products p ON p.id = l.product_id
               WHERE i.supplier_id = ?
               GROUP BY p.id
               ORDER BY p.nome LIMIT 200""",
            (supplier_id,),
        ).fetchall()
    data = supplier_to_dict(row)
    data["prodotti"] = [dict(p) for p in products]
    return data


@app.put("/api/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, payload: SupplierUpdate):
    data = payload.model_dump(exclude_unset=True)
    with db() as conn:
        row = conn.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Fornitore non trovato")
        sconti = data.pop("sconti", None)
        fields = {k: v for k, v in data.items() if v is not None or k in data}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            conn.execute(
                f"UPDATE suppliers SET {sets}, updated_at=datetime('now') WHERE id=?",
                (*fields.values(), supplier_id),
            )
        if sconti is not None:
            conn.execute(
                "UPDATE suppliers SET sconti_json=?, updated_at=datetime('now') WHERE id=?",
                (dump_sconti([s.model_dump() for s in payload.sconti or []]), supplier_id),
            )
        row = conn.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
    return supplier_to_dict(row)


@app.get("/api/products")
def list_products(q: str = ""):
    with db() as conn:
        if q.strip():
            like = f"%{q.strip().lower()}%"
            rows = conn.execute(
                """SELECT p.*, COUNT(l.id) AS righe,
                          COUNT(DISTINCT i.supplier_id) AS fornitori,
                          MIN(l.prezzo_normalizzato) AS prezzo_min,
                          MAX(l.prezzo_normalizzato) AS prezzo_max
                   FROM products p
                   LEFT JOIN lines l ON l.product_id = p.id
                   LEFT JOIN invoices i ON i.id = l.invoice_id
                   WHERE p.nome_norm LIKE ? OR lower(p.nome) LIKE ?
                   GROUP BY p.id
                   ORDER BY p.nome LIMIT 100""",
                (like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT p.*, COUNT(l.id) AS righe,
                          COUNT(DISTINCT i.supplier_id) AS fornitori,
                          MIN(l.prezzo_normalizzato) AS prezzo_min,
                          MAX(l.prezzo_normalizzato) AS prezzo_max
                   FROM products p
                   LEFT JOIN lines l ON l.product_id = p.id
                   LEFT JOIN invoices i ON i.id = l.invoice_id
                   GROUP BY p.id
                   ORDER BY p.nome LIMIT 100"""
            ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    with db() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise HTTPException(404, "Prodotto non trovato")
        history = conn.execute(
            """SELECT l.prezzo_unitario, l.prezzo_normalizzato, l.unita_normalizzata,
                      l.quantita, i.data, i.numero, s.ragione_sociale, s.partita_iva
               FROM lines l
               JOIN invoices i ON i.id = l.invoice_id
               LEFT JOIN suppliers s ON s.id = i.supplier_id
               WHERE l.product_id = ?
               ORDER BY i.data DESC LIMIT 100""",
            (product_id,),
        ).fetchall()
    return {"product": dict(product), "history": [dict(h) for h in history]}


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
