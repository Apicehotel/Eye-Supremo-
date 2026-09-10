import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from pypdf import PdfReader
from .normalization import normalize_text


def decimal(value, default="0") -> Decimal:
    try:
        return Decimal(str(value or default).replace(".", "").replace(",", ".")) if isinstance(value, str) and "," in value else Decimal(str(value or default))
    except InvalidOperation:
        return Decimal(default)


def tag(node, name):
    found = node.find(f".//{{*}}{name}")
    return found.text.strip() if found is not None and found.text else None


def parse_xml(path: Path) -> dict:
    root = ET.parse(path).getroot()
    supplier_node = root.find(".//{*}CedentePrestatore")
    body = root.find(".//{*}FatturaElettronicaBody")
    company = tag(supplier_node, "Denominazione") or " ".join(filter(None, [tag(supplier_node, "Nome"), tag(supplier_node, "Cognome")]))
    rows = []
    for line in root.findall(".//{*}DettaglioLinee"):
        desc = tag(line, "Descrizione") or "Riga senza descrizione"
        rows.append({
            "descrizione_originale": desc, "descrizione_normalizzata": normalize_text(desc),
            "quantita": str(decimal(tag(line, "Quantita"), "1")), "unita_originale": tag(line, "UnitaMisura"),
            "prezzo_unitario": str(decimal(tag(line, "PrezzoUnitario"))), "totale_riga": str(decimal(tag(line, "PrezzoTotale"))),
            "aliquota_iva": str(decimal(tag(line, "AliquotaIVA"))), "confidence": 1.0,
        })
    raw_date = tag(body, "Data") or date.today().isoformat()
    total = decimal(tag(body, "ImportoTotaleDocumento"), str(sum(decimal(x["totale_riga"]) for x in rows)))
    taxable = sum(decimal(x["totale_riga"]) for x in rows)
    return {"supplier": {"ragione_sociale": company or "Fornitore da verificare", "partita_iva": tag(supplier_node, "IdCodice"), "codice_fiscale": tag(supplier_node, "CodiceFiscale")}, "invoice": {"numero": tag(body, "Numero") or "SENZA-NUMERO", "data": raw_date, "imponibile": str(taxable), "iva": str(total-taxable), "totale": str(total), "valuta": tag(body, "Divisa") or "EUR"}, "rows": rows, "confidence": 1.0, "warnings": []}


def parse_pdf(path: Path) -> dict:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if not text.strip():
        return {"supplier": {"ragione_sociale": "Da riconoscere"}, "invoice": {"numero": "DA-VERIFICARE", "data": date.today().isoformat(), "imponibile": "0", "iva": "0", "totale": "0", "valuta": "EUR"}, "rows": [], "confidence": .15, "warnings": ["PDF senza testo: installare Tesseract per l'OCR"], "extracted_text": ""}
    number = re.search(r"(?:fattura|n\.?)[\s:#-]*([A-Z0-9/-]+)", text, re.I)
    total = re.findall(r"(?:totale\s+(?:documento|fattura)?)[\s€:]*([\d.,]+)", text, re.I)
    return {"supplier": {"ragione_sociale": text.splitlines()[0][:180] or "Da verificare"}, "invoice": {"numero": number.group(1) if number else "DA-VERIFICARE", "data": date.today().isoformat(), "imponibile": "0", "iva": "0", "totale": str(decimal(total[-1])) if total else "0", "valuta": "EUR"}, "rows": [], "confidence": .45, "warnings": ["Controllare i campi estratti dal PDF"], "extracted_text": text}


def parse_document(path: Path) -> dict:
    if path.suffix.lower() == ".xml": return parse_xml(path)
    if path.suffix.lower() == ".pdf": return parse_pdf(path)
    raise ValueError("Formato supportato in questa milestone: PDF o XML")
