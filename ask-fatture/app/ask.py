"""Ricerca righe + domanda a Ollama (modello light)."""
from __future__ import annotations

import re

import httpx

from .config import settings
from .db import db


def search_lines(query: str, limit: int = 25) -> list[dict]:
    tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 3]
    stop = {
        "quanto",
        "pago",
        "costa",
        "costo",
        "meno",
        "dove",
        "quale",
        "quali",
        "per",
        "della",
        "delle",
        "degli",
        "sono",
        "come",
        "quando",
        "fattura",
        "fatture",
        "prezzo",
        "prezzi",
    }
    tokens = [t for t in tokens if t not in stop] or tokens
    # Espandi con prefissi (lampadina → lamp) per match grezzi sulle descrizioni
    expanded: list[str] = []
    for t in tokens:
        expanded.append(t)
        if len(t) >= 5:
            expanded.append(t[:4])
    tokens = list(dict.fromkeys(expanded))
    with db() as conn:
        if not tokens:
            rows = conn.execute(
                """
                SELECT l.*, i.numero, i.data, i.fornitore, i.supplier_id,
                       s.partita_iva, s.ragione_sociale, s.sconti_json
                FROM lines l
                JOIN invoices i ON i.id = l.invoice_id
                LEFT JOIN suppliers s ON s.id = i.supplier_id
                ORDER BY i.data DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            clauses = " OR ".join(
                ["lower(l.descrizione) LIKE ? OR ifnull(l.descrizione_norm,'') LIKE ?" for _ in tokens]
            )
            params: list[str] = []
            for t in tokens:
                params.extend([f"%{t}%", f"%{t}%"])
            rows = conn.execute(
                f"""
                SELECT l.*, i.numero, i.data, i.fornitore, i.supplier_id,
                       s.partita_iva, s.ragione_sociale, s.sconti_json
                FROM lines l
                JOIN invoices i ON i.id = l.invoice_id
                LEFT JOIN suppliers s ON s.id = i.supplier_id
                WHERE {clauses}
                ORDER BY i.data DESC LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
    return [dict(r) for r in rows]


async def ollama_ready() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            r.raise_for_status()
            names = [m.get("name", "") for m in r.json().get("models", [])]
            has = any(settings.model in n or n.startswith(settings.model.split(":")[0]) for n in names)
            exact = any(n == settings.model or n.startswith(settings.model + ":") for n in names)
            return {
                "available": True,
                "model": settings.model,
                "model_present": exact or has,
                "models": names[:20],
            }
    except Exception as exc:
        return {"available": False, "model": settings.model, "model_present": False, "error": str(exc)}


async def ask(question: str) -> dict:
    records = search_lines(question)
    status = await ollama_ready()
    sources = [
        {
            "descrizione": r["descrizione"],
            "prezzo_unitario": r.get("prezzo_unitario"),
            "prezzo_normalizzato": r.get("prezzo_normalizzato"),
            "unita_normalizzata": r.get("unita_normalizzata"),
            "quantita": r.get("quantita"),
            "unita": r.get("unita"),
            "fornitore": r.get("ragione_sociale") or r["fornitore"],
            "partita_iva": r.get("partita_iva"),
            "fattura": r["numero"],
            "data": r["data"],
        }
        for r in records
    ]

    if not records:
        return {
            "mode": "empty",
            "answer": "Non ho trovato righe in archivio per questa domanda. Importa prima delle fatture XML.",
            "sources": [],
            "model": settings.model,
        }

    if not status.get("available") or not status.get("model_present"):
        # Fallback: confronta su prezzo normalizzato se c'è, altrimenti unitario
        def key_price(s):
            p = s.get("prezzo_normalizzato")
            if p is None:
                p = s.get("prezzo_unitario")
            return float(p) if p is not None else float("inf")

        priced = [s for s in sources if key_price(s) != float("inf")]
        if priced:
            best = min(priced, key=key_price)
            um = best.get("unita_normalizzata") or best.get("unita") or "u"
            pn = best.get("prezzo_normalizzato")
            pu = best.get("prezzo_unitario")
            answer = (
                f"(Senza Ollama) Trovate {len(priced)} righe. "
                f"Miglior prezzo: {pn if pn is not None else pu} €/{um} "
                f"(dichiarato {pu} €) da {best['fornitore']} "
                f"(fattura {best['fattura']} del {best['data']}) "
                f"per «{best['descrizione']}»."
            )
        else:
            answer = f"Trovate {len(sources)} righe ma senza prezzo. Avvia Ollama e scarica {settings.model}."
        return {"mode": "local", "answer": answer, "sources": sources, "model": settings.model}

    context = "\n".join(
        f"- {s['descrizione']} | prezzo dichiarato {s['prezzo_unitario']} €/{s.get('unita') or 'u'} | "
        f"prezzo normalizzato {s.get('prezzo_normalizzato')} €/{s.get('unita_normalizzata') or 'u'} | "
        f"qty {s['quantita']} | fornitore {s['fornitore']} | fattura {s['fattura']} | data {s['data']}"
        for s in sources
    )
    system = (
        "Sei Ask Fatture, assistente locale sulle fatture aziendali. "
        "Rispondi in italiano, in modo breve e concreto. "
        "Usa SOLO i dati forniti. Per confronti usa il PREZZO NORMALIZZATO "
        "(€/kg, €/l o €/pz). Il prezzo unitario è quello in fattura. "
        "Ignora mentalmente carburante, sconti e bollo: non sono in archivio. "
        "Quando confronti prezzi indica fornitore, data, prezzo normalizzato e unitario."
    )
    prompt = f"Dati estratti dall'archivio:\n{context}\n\nDomanda: {question}"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{settings.ollama_url}/api/chat",
                json={
                    "model": settings.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "options": {"temperature": 0.2, "num_ctx": 4096},
                },
            )
            r.raise_for_status()
            content = r.json().get("message", {}).get("content") or ""
        return {"mode": "ollama", "answer": content.strip(), "sources": sources, "model": settings.model}
    except Exception as exc:
        return {
            "mode": "error",
            "answer": f"Errore Ollama: {exc}",
            "sources": sources,
            "model": settings.model,
        }
