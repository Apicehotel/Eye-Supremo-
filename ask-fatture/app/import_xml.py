"""Parser minimale FatturaPA → fatture + righe normalizzate (senza rumore)."""
from __future__ import annotations

from pathlib import Path

from lxml import etree

from .normalize import normalize_line


def _text(el) -> str:
    if el is None or el.text is None:
        return ""
    return " ".join(el.text.split())


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _extract_supplier(root) -> dict:
    cedente = None
    for el in root.iter():
        if _local(el.tag) == "CedentePrestatore":
            cedente = el
            break

    ragione = ""
    nome = cognome = ""
    piva = cf = ""
    indirizzo = cap = citta = provincia = nazione = ""

    scope = cedente if cedente is not None else root
    for el in scope.iter():
        name = _local(el.tag)
        val = _text(el)
        if not val:
            continue
        if name == "Denominazione" and not ragione:
            ragione = val
        elif name == "Nome" and not nome:
            nome = val
        elif name == "Cognome" and not cognome:
            cognome = val
        elif name == "IdCodice" and not piva:
            # IdFiscaleIVA/IdCodice = P.IVA
            piva = val
        elif name == "CodiceFiscale" and not cf:
            cf = val
        elif name == "Indirizzo" and not indirizzo:
            indirizzo = val
        elif name == "CAP" and not cap:
            cap = val
        elif name == "Comune" and not citta:
            citta = val
        elif name == "Provincia" and not provincia:
            provincia = val
        elif name == "Nazione" and not nazione:
            nazione = val

    if not ragione:
        ragione = " ".join(x for x in [nome, cognome] if x).strip()
    nome_commerciale = None
    if nome or cognome:
        nome_commerciale = " ".join(x for x in [nome, cognome] if x).strip() or None

    return {
        "ragione_sociale": ragione or "Fornitore sconosciuto",
        "nome_commerciale": nome_commerciale,
        "partita_iva": piva or None,
        "codice_fiscale": cf or None,
        "indirizzo": indirizzo or None,
        "cap": cap or None,
        "citta": citta or None,
        "provincia": provincia or None,
        "nazione": nazione or "IT",
        "email": None,
        "telefono": None,
        "pec": None,
        "sconti": [],
        "note": None,
    }


def parse_fatturapa(path: Path) -> dict:
    root = etree.parse(str(path)).getroot()
    supplier = _extract_supplier(root)

    numero = data = ""
    totale = 0.0
    for el in root.iter():
        name = _local(el.tag)
        if name == "Numero" and not numero:
            numero = _text(el)
        elif name == "Data" and not data and len(_text(el)) >= 8:
            data = _text(el)[:10]
        elif name == "ImportoTotaleDocumento":
            try:
                totale = float(_text(el).replace(",", "."))
            except ValueError:
                pass

    rows: list[dict] = []
    skipped: list[dict] = []
    for dettaglio in root.iter():
        if _local(dettaglio.tag) != "DettaglioLinee":
            continue
        desc = qty = unit = price = line_total = ""
        for child in dettaglio:
            n = _local(child.tag)
            if n == "Descrizione":
                desc = _text(child)
            elif n == "Quantita":
                qty = _text(child)
            elif n == "UnitaMisura":
                unit = _text(child)
            elif n == "PrezzoUnitario":
                price = _text(child)
            elif n == "PrezzoTotale":
                line_total = _text(child)
        if not desc:
            continue

        def num(v: str) -> float | None:
            try:
                return float(v.replace(",", "."))
            except (ValueError, AttributeError):
                return None

        normalized = normalize_line(
            description=desc,
            quantita=num(qty),
            unita=unit or None,
            prezzo_unitario=num(price),
            totale_riga=num(line_total),
        )
        if normalized["is_noise"]:
            skipped.append({"descrizione": desc, "motivo": "rumore (sconto/carburante/bollo/…)"})
            continue
        rows.append(normalized)

    return {
        "numero": numero or path.stem,
        "data": data or None,
        "supplier": supplier,
        "fornitore": supplier["ragione_sociale"],
        "totale": totale,
        "rows": rows,
        "skipped": skipped,
    }
