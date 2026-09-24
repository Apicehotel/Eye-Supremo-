"""Catalogo fornitori e prodotti (per fornitore / per prodotto)."""
from __future__ import annotations

from .db import dump_sconti, parse_sconti


def upsert_supplier(conn, data: dict) -> int:
    """Crea o aggiorna fornitore per P.IVA oppure ragione sociale."""
    piva = (data.get("partita_iva") or "").strip() or None
    name = (data.get("ragione_sociale") or "").strip() or "Fornitore sconosciuto"
    row = None
    if piva:
        row = conn.execute("SELECT * FROM suppliers WHERE partita_iva = ?", (piva,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM suppliers WHERE lower(ragione_sociale) = lower(?) LIMIT 1",
            (name,),
        ).fetchone()

    fields = {
        "ragione_sociale": name,
        "nome_commerciale": (data.get("nome_commerciale") or "").strip() or None,
        "partita_iva": piva,
        "codice_fiscale": (data.get("codice_fiscale") or "").strip() or None,
        "indirizzo": (data.get("indirizzo") or "").strip() or None,
        "cap": (data.get("cap") or "").strip() or None,
        "citta": (data.get("citta") or "").strip() or None,
        "provincia": (data.get("provincia") or "").strip() or None,
        "nazione": (data.get("nazione") or "IT").strip() or "IT",
        "email": (data.get("email") or "").strip() or None,
        "telefono": (data.get("telefono") or "").strip() or None,
        "pec": (data.get("pec") or "").strip() or None,
        "note": (data.get("note") or "").strip() or None,
    }

    if row:
        sid = row["id"]
        # Non azzerare sconti già impostati dall'utente in import automatico
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE suppliers SET {sets}, updated_at=datetime('now') WHERE id=?",
            (*fields.values(), sid),
        )
        return sid

    sconti = dump_sconti(data.get("sconti") if isinstance(data.get("sconti"), list) else [])
    cur = conn.execute(
        """INSERT INTO suppliers(
             ragione_sociale, nome_commerciale, partita_iva, codice_fiscale,
             indirizzo, cap, citta, provincia, nazione, email, telefono, pec,
             sconti_json, note
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            fields["ragione_sociale"],
            fields["nome_commerciale"],
            fields["partita_iva"],
            fields["codice_fiscale"],
            fields["indirizzo"],
            fields["cap"],
            fields["citta"],
            fields["provincia"],
            fields["nazione"],
            fields["email"],
            fields["telefono"],
            fields["pec"],
            sconti,
            fields["note"],
        ),
    )
    return int(cur.lastrowid)


def upsert_product(conn, nome: str, nome_norm: str | None, unita_base: str | None) -> int:
    key = (nome_norm or nome or "").strip().lower()
    if not key:
        key = nome.strip().lower()
    row = conn.execute("SELECT id FROM products WHERE nome_norm = ?", (key,)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO products(nome, nome_norm, unita_base) VALUES (?,?,?)",
        (nome.strip()[:240], key[:240], unita_base),
    )
    return int(cur.lastrowid)


def supplier_to_dict(row) -> dict:
    d = dict(row)
    d["sconti"] = parse_sconti(d.pop("sconti_json", None))
    return d
