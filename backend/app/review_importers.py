from __future__ import annotations

import re
from datetime import date, datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path


def _parse_date(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return fallback


def _rating(text: str):
    patterns = (
        r"(?:voto|rating|score|valutazione)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)",
        r"\b(\d+(?:[.,]\d+)?)\s*/\s*10\b",
        r"\b(\d+(?:[.,]\d+)?)\s*/\s*5\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).replace(",", ".")
    return None


def _author(text: str, fallback: str | None = None):
    match = re.search(r"(?:ospite|cliente|autore|guest|reviewer|nome)\s*[:\-]\s*([^\r\n]{2,100})", text, re.I)
    return (match.group(1).strip()[:160] if match else (fallback[:160] if fallback else None))


def _source(text: str, fallback: str = "email") -> str:
    low = text.lower()
    if "booking" in low:
        return "Booking"
    if "tripadvisor" in low:
        return "TripAdvisor"
    if "google" in low:
        return "Google"
    return fallback


def _review_date(text: str, fallback: str) -> str:
    match = re.search(r"(?:data\s+recensione|recensione\s+del|pubblicata\s+il|review\s+date)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})", text, re.I)
    return _parse_date(match.group(1) if match else None, fallback)


def _room(text: str):
    match = re.search(r"(?:\bCAM\b|camera|room)\s*[:#\-]?\s*([A-Z0-9-]{1,12})", text, re.I)
    return match.group(1) if match else None


def _looks_like_review(text: str) -> bool:
    low = text.lower()
    platform = any(x in low for x in ("booking", "tripadvisor", "google"))
    review_terms = any(x in low for x in ("recensione", "review", "valutazione", "voto", "positivo", "negativo"))
    room_terms = bool(re.search(r"(?:\bCAM\b|camera|room)\s*[:#\-]?\s*[A-Z0-9-]{1,12}", text, re.I))
    return (platform and review_terms) or (room_terms and review_terms)


def split_review_blocks(text: str, default_date: str, source_hint: str, author_hint: str | None, raw_file: str) -> list[dict]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []

    # Real Hotel Giò messages often contain many Booking reviews and expose each room as CAM: NNN.
    starts = [m.start() for m in re.finditer(r"(?im)(?:^|\n)\s*(?:CAM|CAMERA|ROOM)\s*[:#\-]?\s*[A-Z0-9-]{1,12}", cleaned)]
    blocks: list[str] = []
    if len(starts) >= 2:
        prefix_start = max(0, starts[0] - 800)
        for idx, start in enumerate(starts):
            end = starts[idx + 1] if idx + 1 < len(starts) else len(cleaned)
            block = cleaned[start:end].strip()
            if idx == 0 and prefix_start < start:
                prefix = cleaned[prefix_start:start]
                if any(p in prefix.lower() for p in ("booking", "tripadvisor", "google")):
                    block = prefix + "\n" + block
            blocks.append(block)
    else:
        # Fallback for Google/TripAdvisor mail digests: split on repeated platform headings when possible.
        parts = re.split(r"(?im)(?=^\s*(?:booking(?:\.com)?|tripadvisor|google)\b)", cleaned)
        blocks = [p.strip() for p in parts if p.strip()] if len(parts) > 1 else [cleaned]

    reviews: list[dict] = []
    for block in blocks:
        if not _looks_like_review(block):
            continue
        reviews.append({
            "date": _review_date(block, default_date),
            "author": _author(block, author_hint),
            "source": _source(block, source_hint),
            "text": block,
            "rating": _rating(block),
            "room_code": _room(block),
            "raw_file": raw_file,
        })
    return reviews


def _parse_eml(path: Path) -> tuple[str, str, str | None, str]:
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
            payload = message.get_payload(decode=True)
            body_parts.append(payload.decode("utf-8", errors="replace") if payload else "")
    text = "\n".join(x.strip() for x in body_parts if x and x.strip())
    raw_date = message.get("date")
    try:
        default_date = parsedate_to_datetime(raw_date).date().isoformat() if raw_date else date.today().isoformat()
    except Exception:
        default_date = date.today().isoformat()
    sender = str(message.get("from") or "") or None
    subject = str(message.get("subject") or "")
    return subject + "\n" + text, default_date, sender, "email"


def _parse_msg(path: Path) -> tuple[str, str, str | None, str]:
    try:
        import extract_msg
    except ImportError as exc:
        raise RuntimeError("Supporto MSG non installato: reinstallare Eye Supremo con il pacchetto aggiornato") from exc
    message = extract_msg.Message(str(path))
    try:
        subject = str(message.subject or "")
        body = str(message.body or "")
        sender = str(message.sender or "") or None
        raw_date = str(message.date or "")
        default_date = date.today().isoformat()
        match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", raw_date)
        if match:
            default_date = _parse_date(match.group(1), default_date)
        return subject + "\n" + body, default_date, sender, "Outlook MSG"
    finally:
        try:
            message.close()
        except Exception:
            pass


def parse_review_document(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".eml":
        text, default_date, sender, hint = _parse_eml(path)
    elif suffix == ".msg":
        text, default_date, sender, hint = _parse_msg(path)
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace")
        default_date, sender, hint = date.today().isoformat(), None, "TXT"
    else:
        raise ValueError("Formato recensione supportato: MSG, EML o TXT")
    return split_review_blocks(text, default_date, hint, sender, path.name)
