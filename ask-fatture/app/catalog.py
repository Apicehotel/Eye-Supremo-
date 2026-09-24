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


def product_pack(row) -> dict | None:
    if not row:
        return None
    contenuto = row["pack_contenuto"] if "pack_contenuto" in row.keys() else None
    unita = row["pack_unita"] if "pack_unita" in row.keys() else None
    if contenuto is None or not unita:
        return None
    return {"contenuto": float(contenuto), "unita": str(unita)}


def set_product_pack(
    conn,
    product_id: int,
    *,
    contenuto: float,
    unita: str,
    note: str | None = None,
    updated_by: str | None = None,
) -> dict:
    from .normalize import lookup_unit, normalize_line
    from decimal import Decimal

    raw = unita.strip().lower()
    base, factor = lookup_unit(raw)
    if not base or base not in {"kg", "l", "pz"}:
        raise ValueError("Unità pack non valida: scegli Chili, Litri o Pezzi")
    if contenuto <= 0:
        raise ValueError("Contenuto pack deve essere > 0")
    # UI cucina: Chili / Litri / Pezzi — se arriva g/ml ecc. converti in chili/litri
    store_unit = {"kg": "chili", "l": "litri", "pz": "pezzi"}[base]
    store_qty = float(Decimal(str(contenuto)) * factor)
    store_factor = Decimal("1")

    conn.execute(
        """UPDATE products
           SET pack_contenuto=?, pack_unita=?, pack_note=?, pack_updated_by=?,
               unita_base=COALESCE(unita_base, ?)
           WHERE id=?""",
        (store_qty, store_unit, note, updated_by or "cucina", base, product_id),
    )

    # Ricalcola tutte le righe di questo prodotto con il pack noto
    lines = conn.execute(
        "SELECT id, descrizione, quantita, unita, prezzo_unitario, totale_riga FROM lines WHERE product_id=?",
        (product_id,),
    ).fetchall()
    pack = {"contenuto": store_qty, "unita": store_unit}
    updated = 0
    for line in lines:
        norm = normalize_line(
            description=line["descrizione"],
            quantita=line["quantita"],
            unita=line["unita"],
            prezzo_unitario=line["prezzo_unitario"],
            totale_riga=line["totale_riga"],
            known_pack=pack,
        )
        conn.execute(
            """UPDATE lines
               SET unita_normalizzata=?, prezzo_normalizzato=?, contenuto_base=?
               WHERE id=?""",
            (
                norm["unita_normalizzata"],
                norm["prezzo_normalizzato"],
                norm["contenuto_base"],
                line["id"],
            ),
        )
        updated += 1

    row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    return {
        "product": dict(row),
        "lines_updated": updated,
        "pack_base": store_qty,
        "base": base,
    }


def supplier_to_dict(row) -> dict:
    d = dict(row)
    d["sconti"] = parse_sconti(d.pop("sconti_json", None))
    return d
