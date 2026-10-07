import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path
from pypdf import PdfReader
from .normalization import normalize_text


def decimal(value, default="0") -> Decimal:
    try:
        return Decimal(str(value or default).replace(".", "").replace(",", ".")) if isinstance(value, str) and "," in value else Decimal(str(value or default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def tag(node, name):
    if node is None:
        return None
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
        return {"supplier": {"ragione_sociale": "Da riconoscere"}, "invoice": {"numero": "DA-VERIFICARE", "data": date.today().isoformat(), "imponibile": "0", "iva": "0", "totale": "0", "valuta": "EUR"}, "rows": [], "confidence": .15, "warnings": ["PDF senza testo: installare OCR opzionale"], "extracted_text": ""}
    number = re.search(r"(?:fattura|n\.?)[\s:#-]*([A-Z0-9/-]+)", text, re.I)
    total = re.findall(r"(?:totale\s+(?:documento|fattura)?)[\s€:]*([\d.,]+)", text, re.I)
    return {"supplier": {"ragione_sociale": text.splitlines()[0][:180] or "Da verificare"}, "invoice": {"numero": number.group(1) if number else "DA-VERIFICARE", "data": date.today().isoformat(), "imponibile": "0", "iva": "0", "totale": str(decimal(total[-1])) if total else "0", "valuta": "EUR"}, "rows": [], "confidence": .45, "warnings": ["Controllare i campi estratti dal PDF"], "extracted_text": text}


def parse_txt(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    number = re.search(r"(?:fattura|documento|n\.?)[\s:#-]*([A-Z0-9/-]+)", text, re.I)
    raw_date = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", text)
    parsed_date = date.today().isoformat()
    if raw_date:
        candidate = raw_date.group(1)
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                parsed_date = datetime.strptime(candidate, fmt).date().isoformat(); break
            except ValueError:
                pass
    total_matches = re.findall(r"(?:totale\s+(?:documento|fattura)?)[\s€:]*([\d.,]+)", text, re.I)
    rows = []
    # Conservative generic parser: only lines ending with quantity/unit-price/total triplets become purchase rows.
    row_re = re.compile(r"^(?P<desc>.+?)\s+(?P<qty>\d+[\d.,]*)\s*(?P<unit>KG|G|GR|LT|L|ML|PZ|PZ\.|PCS|CF|CONF|NR)?\s+(?P<price>\d+[\d.,]*)\s+(?P<total>\d+[\d.,]*)$", re.I)
    for line in lines:
        match = row_re.match(line)
        if not match:
            continue
        desc = match.group("desc").strip()
        rows.append({"descrizione_originale": desc, "descrizione_normalizzata": normalize_text(desc),
                     "quantita": str(decimal(match.group("qty"), "1")), "unita_originale": match.group("unit"),
                     "prezzo_unitario": str(decimal(match.group("price"))), "totale_riga": str(decimal(match.group("total"))),
                     "aliquota_iva": None, "confidence": .72})
    taxable = sum(decimal(x["totale_riga"]) for x in rows)
    total = decimal(total_matches[-1]) if total_matches else taxable
    return {"supplier": {"ragione_sociale": (lines[0][:180] if lines else "Fornitore da verificare")},
            "invoice": {"numero": number.group(1) if number else "DA-VERIFICARE", "data": parsed_date,
                        "imponibile": str(taxable), "iva": str(max(Decimal("0"), total-taxable)), "totale": str(total), "valuta": "EUR"},
            "rows": rows, "confidence": .72 if rows else .35,
            "warnings": ([] if rows else ["TXT letto ma righe da verificare manualmente"]), "extracted_text": text}


def parse_review_email(path: Path) -> dict:
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    body_parts = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
                try:
                    body_parts.append(part.get_content())
                except Exception:
                    pass
    else:
        try:
            body_parts.append(message.get_content())
        except Exception:
            body_parts.append(message.get_payload(decode=True).decode("utf-8", errors="replace") if message.get_payload(decode=True) else "")
    text = "\n".join(x.strip() for x in body_parts if x and x.strip())
    raw_date = message.get("date")
    try:
        review_date = parsedate_to_datetime(raw_date).date().isoformat() if raw_date else date.today().isoformat()
    except Exception:
        review_date = date.today().isoformat()
    subject = str(message.get("subject") or "")
    sender = str(message.get("from") or "")
    rating_match = re.search(r"(?:voto|rating|score|valutazione)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)", subject + "\n" + text, re.I)
    room_match = re.search(r"(?:camera|room)\s*[:#-]?\s*([A-Z0-9-]{1,12})", subject + "\n" + text, re.I)
    return {"date": review_date, "author": sender[:160] or None, "source": "email", "subject": subject,
            "text": text or subject, "rating": str(decimal(rating_match.group(1))) if rating_match else None,
            "room_code": room_match.group(1) if room_match else None, "raw_file": path.name}


def parse_document(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".xml": return parse_xml(path)
    if suffix == ".pdf": return parse_pdf(path)
    if suffix == ".txt": return parse_txt(path)
    raise ValueError("Formato fattura supportato: XML, TXT o PDF")
