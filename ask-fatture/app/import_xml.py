"""Parser minimale FatturaPA → fattura + righe."""
from __future__ import annotations

from pathlib import Path

from lxml import etree


def _text(el) -> str:
    if el is None or el.text is None:
        return ""
    return " ".join(el.text.split())


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def parse_fatturapa(path: Path) -> dict:
    root = etree.parse(str(path)).getroot()
    fornitore = ""
    for el in root.iter():
        if _local(el.tag) == "Denominazione" and not fornitore:
            # prima denominazione di solito è cedente
            parent_names = [_local(p.tag) for p in el.iterancestors()]
            if any("Cedente" in n or "Prestatore" in n for n in parent_names):
                fornitore = _text(el)
                break
    if not fornitore:
        for el in root.iter():
            if _local(el.tag) == "Denominazione":
                fornitore = _text(el)
                break

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

        rows.append(
            {
                "descrizione": desc,
                "quantita": num(qty),
                "unita": unit or None,
                "prezzo_unitario": num(price),
                "totale_riga": num(line_total),
            }
        )

    return {
        "numero": numero or path.stem,
        "data": data or None,
        "fornitore": fornitore or "Fornitore sconosciuto",
        "totale": totale,
        "rows": rows,
    }
