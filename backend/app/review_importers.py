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
    # TripAdvisor often omits the overall score and writes only category
    # scores compacted in the digest (for example ``Camere3,0 Servizio3,0``).
    # Treat those values as real votes and use their average as the review
    # score, while the category text remains available for classification.
    category_pattern = r"(?:camere?|servizio|posizione|pulizia|comfort|staff|letti?|ristorante|colazione|rapporto[ \t]+qualità/prezzo)[ \t]*[:\-]?[ \t]*(\d+(?:[.,]\d+)?)"
    # An explicit overall score always has priority over category scores.
    patterns = (
        r"(?:voto|rating|score|valutazione)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)",
        r"\b(\d+(?:[.,]\d+)?)\s*/\s*10\b",
        r"\b(\d+(?:[.,]\d+)?)\s*/\s*5\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).replace(",", ".")
    # Booking exports may put the overall score on the line immediately
    # before the guest name (``9,0 Luca, it``) without a label.
    standalone_author_score = re.search(
        r"(?m)^\s*(10(?:[.,]0)?|[0-9](?:[.,][0-9])?)\s+(?=[A-ZÀ-ÿ][^\n]{1,80})",
        text,
    )
    if standalone_author_score:
        return standalone_author_score.group(1).replace(",", ".")
    category_scores = [
        float(value.replace(",", "."))
        for value in re.findall(
            category_pattern,
            text,
            re.I,
        )
    ]
    category_scores = [value for value in category_scores if 0 <= value <= 10]
    if category_scores:
        return f"{sum(category_scores) / len(category_scores):.1f}"
    return None


def _author(text: str, fallback: str | None = None):
    match = re.search(r"(?:ospite|cliente|autore|guest|reviewer|nome)\s*[:\-]\s*([^\r\n]{2,100})", text, re.I)
    if match:
        value = match.group(1).strip()
        return None if "@" in value else value[:160]
    google_name = re.search(r"(?:google|tripadvisor)[^\n]{0,100}?\b(?:nessuna recensione|nessun voto)\s+([A-Za-zÀ-ÿ']{3,})\b", text, re.I)
    if google_name and "@" not in google_name.group(1):
        candidate = google_name.group(1).strip()
        if candidate.lower() not in {"hotel gio", "hotel", "nessuna recensione"}:
            return candidate[:160]
    return fallback[:160] if fallback and "@" not in fallback else None


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
    match = re.search(r"(?:\bCAM\b|camera|room)[ \t]*[:#.\-]?[ \t]*([A-Z0-9-]{1,12})", text, re.I)
    value = match.group(1) if match else None
    if value and re.fullmatch(r"\d{1,4}[A-Z]?", value, re.I):
        return value
    # Booking digests often put the room number after the room type, e.g.
    # ``Matrimoniale Superior Jazz 4410 Numero di prenotazione ...``.
    booking_match = re.search(
        r"(?:matrimoniale|suite|tripla|quadrupla|doppia|singola|junior|deluxe|superior|standard)[^\n]{0,80}?\b(\d{3,4}[A-Z]?)\b(?=\s+numero di prenotazione)",
        text,
        re.I,
    )
    return booking_match.group(1) if booking_match else None


def clean_review_text(text: str) -> str:
    """Keep only the guest-written review text, removing email/platform metadata."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"<https?://[^>]+>|<mailto:[^>]+>|https?://\S+", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    google_mode = bool(re.search(r"\bgoogle\b", cleaned, re.I))
    sections = re.split(r"(?im)^\s*_{10,}\s*$", cleaned)
    if len(sections) > 1:
        cleaned = sections[-1]
    # Inline Booking separators often put the guest text after the
    # translation/footer marker on the same line.
    cleaned = re.sub(r"(?is)^.*?tradotto .*?vedi l['’]originale\s*", "", cleaned)
    technical = re.compile(
        r"^(?:numero di prenotazione\b|categorie\s+(?:base|extra)\b|"
        r"staff|pulizia|posizione|servizi|comfort|rapporto qualità/prezzo|"
        r"letti|vista dalla camera|wifi|parcheggio|cuscini|"
        r"google|tripadvisor|booking(?:\.com)?|"
        r"(?:vacanza|affari|coppia|famiglia|viaggio)\s*[✦❘|·].*|"
        r"punti forti dell['’]hotel.*|costo giusto|"
        r"[^\n]{1,100}\s+ha scritto una recensione.*|\d+\s+contributi.*|"
        r"recensioni hotel.*|numero di prenotazione.*|\d{1,2}\s+ago\s+\d{4}.*|"
        r"(?:matrimoniale|suite|tripla|quadrupla|doppia|singola|junior|deluxe|superior|standard)[^\n]{0,100}\d{3,4}\s+numero di prenotazione.*|"
        r"[A-ZÀ-Ý][^,\n]{1,100},\s*[a-z]{2}\s+[A-ZÀ-Ý][^\n]{1,100}|"
        r"(?:camere|servizio|posizione)\s*\d+(?:[.,]\d+)?|"
        r"#[0-9]+|\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}|"
        r"[^\n]{2,80}\s+su google|[^\n]{2,80}\s+google|"
        r"rispondi|nuovo!|tradotto .*vedi l'originale|"
        r"nessuna recensione.*|da:|inviato:|a:|oggetto:|"
        r"hotel gio.*|codice identificativo nazionale.*|cin\s+[A-Z0-9]+|tel\.?\s*\d|"
        r"novità:.*|reception@.*|www\..*|https?:.*|tel.*|amin|michele|"
        r"\*?eventuali offerte presenti.*|scopri i nostri suggerimenti.*|"
        r"reception@.*|www\..*|michele)$",
        re.I,
    )
    guest_metadata = re.compile(r"^[^,\n]{1,100},\s*[a-z]{2}\b.*\b(?:in|out|camera|cam)\b", re.I)
    lines = []
    for line in cleaned.splitlines():
        value = re.sub(r"\s+", " ", line).strip()
        if not value or technical.match(value) or guest_metadata.match(value) or re.fullmatch(r"\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?", value):
            continue
        if google_mode and re.fullmatch(r"[A-ZÀ-Ý][a-zà-ÿ'’-]{2,}(?:\s+[A-ZÀ-Ý][a-zà-ÿ'’-]{2,}){0,3}(?:\s+DJ)?", value):
            continue
        if re.match(r"^(?:cam(?:era)?|room)\b", value, re.I) and re.search(r"\b\d{1,4}[A-Z]?\b", value, re.I):
            continue
        # Google sometimes concatenates the category label directly to the
        # guest prose (e.g. ``CamereLa mia camera...``).
        value = re.sub(r"^(?:Camere|Attività nelle vicinanze|Sicurezza|Percorribilità a piedi|Mangiare e bere|Dettagli importanti)\s*", "", value, flags=re.I)
        lines.append(value)
    return "\n".join(lines).strip()


def _markitdown_text(path: Path) -> str | None:
    """Use MarkItDown when installed, retaining the native parser as fallback."""
    try:
        from markitdown import MarkItDown
        converter = MarkItDown(enable_plugins=False)
        result = converter.convert_local(str(path)) if hasattr(converter, "convert_local") else converter.convert(str(path))
        text = getattr(result, "text_content", None) or getattr(result, "markdown", None)
        return text.strip() if isinstance(text, str) and text.strip() else None
    except Exception:
        return None


def _looks_like_review(text: str) -> bool:
    low = text.lower()
    platform = any(x in low for x in ("booking", "tripadvisor", "google"))
    review_terms = any(x in low for x in ("recensione", "review", "valutazione", "voto", "positivo", "negativo"))
    room_terms = bool(re.search(r"(?:\bCAM\b|camera|room)[ \t]*[:#.\-]?[ \t]*[A-Z0-9-]{1,12}", text, re.I))
    return (platform and review_terms) or (room_terms and review_terms)


def split_review_blocks(text: str, default_date: str, source_hint: str, author_hint: str | None, raw_file: str) -> list[dict]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []

    # Real Hotel Giò messages often contain many Booking reviews. Depending on
    # the export, the room marker may be on its own line (``CAM: 217``) or in
    # the guest line (``camera 2219`` / ``cam:2209``).
    room_pattern = r"(?i)(?<![A-Z0-9])(?:CAM|CAMERA|ROOM)[ \t]*[:#.\-]?[ \t]*\d{1,4}[A-Z]?\b"
    room_matches = list(re.finditer(room_pattern, cleaned))
    starts = [m.start() for m in room_matches]
    if source_hint.lower() == "booking":
        # Booking digests sometimes mark only the first room with ``CAM:``;
        # subsequent reviews use the room type followed by the room number
        # and ``Numero di prenotazione``.
        booking_room_pattern = r"(?im)(?<![A-Z0-9])(?:CAM|CAMERA|ROOM)[ \t]*[:#.\-]?[ \t]*\d{1,4}[A-Z]?\b|(?<![A-Z0-9])(?:MATRIMONIALE|SUITE|TRIPLA|QUADRUPLA|DOPPIA|SINGOLA|JUNIOR|DELUXE|SUPERIOR|STANDARD)[^\n]{0,80}\b\d{3,4}\b(?=\s+Numero di prenotazione)"
        starts = sorted({match.start() for match in re.finditer(booking_room_pattern, cleaned)})
        # Some Booking exports contain an invalid/missing room code (for
        # example ``camera ???``). Use the metadata line immediately before
        # each reservation number as an additional review boundary so the
        # following reservation cannot remain attached to the previous one.
        reservation_pattern = re.compile(r"(?i)nu\s*mero di prenotazione\b")
        for reservation in reservation_pattern.finditer(cleaned):
            window_start = max(0, reservation.start() - 800)
            prefix = cleaned[window_start:reservation.start()]
            line_matches = list(re.finditer(r"(?im)^[^\n]*(?:\bcam\b|\bcamera\b|\broom\b|\bmatrimoniale\b|\bsuite\b|\bin\b[^\n]*\bout\b|,\s*[a-z]{2}\b|\banonimo\b)[^\n]*$", prefix))
            if not line_matches:
                continue
            for line in reversed(line_matches):
                line_text = line.group().strip()
                if re.search(r"\bin\b.*\bout\b|(?:\bcam\b|\bcamera\b|\broom\b)\s*[:#.-]?\s*(?:\d{1,4}[A-Z]?|\?+)|,\s*[a-z]{2}\b|\banonimo\b", line_text, re.I):
                    starts.append(window_start + line.start())
                    break
        starts = sorted(set(starts))
    blocks: list[str] = []
    if len(starts) >= 2:
        for idx, start in enumerate(starts):
            end = starts[idx + 1] if idx + 1 < len(starts) else len(cleaned)
            blocks.append(cleaned[start:end].strip())
    else:
        # Fallback for Google/TripAdvisor mail digests: split on repeated platform headings when possible.
        parts = re.split(r"(?im)(?=^\s*(?:booking(?:\.com)?|tripadvisor|google)\b)", cleaned)
        blocks = [p.strip() for p in parts if p.strip()] if len(parts) > 1 else [cleaned]

    # Some digests append a second review to the same message, introduced by
    # ``<name> ha scritto una recensione``. Keep those reviews separate even
    # when only the first one has a room marker.
    review_marker = re.compile(r"(?im)^\s*[^\n]{1,100}\s+ha scritto una recensione\b")
    separated: list[str] = []
    for block in blocks:
        markers = list(review_marker.finditer(block))
        if not markers:
            separated.append(block)
            continue
        separated.append(block[:markers[0].start()].strip())
        for marker_index, marker in enumerate(markers):
            end = markers[marker_index + 1].start() if marker_index + 1 < len(markers) else len(block)
            separated.append(block[marker.start():end].strip())
    blocks = [block for block in separated if block]

    reviews: list[dict] = []
    for idx, block in enumerate(blocks):
        has_room_marker = bool(re.search(room_pattern, block)) or (
            source_hint.lower() == "booking" and _room(block) is not None
        )
        has_booking_boundary = source_hint.lower() == "booking" and bool(re.search(r"(?i)nu\s*mero di prenotazione\b", block))
        has_review_marker = bool(review_marker.search(block))
        if not _looks_like_review(block) and not has_room_marker and not has_booking_boundary and not has_review_marker:
            continue
        # The score and guest name are commonly immediately before the room
        # marker. Use a bounded context only for metadata extraction; keep the
        # visible text limited to the current review block.
        context = block
        if starts and idx < len(starts):
            prefix_start = max(0, starts[idx] - 800)
            context = cleaned[prefix_start:starts[idx]] + "\n" + block
        # Prefer the nearest unlabeled Booking score before this room marker;
        # the bounded context can contain the previous review's score.
        prefix = cleaned[max(0, starts[idx] - 800):starts[idx]] if starts and idx < len(starts) else ""
        nearby_scores = re.findall(
            r"(?m)^\s*(10(?:[.,]0)?|[0-9](?:[.,][0-9])?)\s+(?=[A-ZÀ-ÿ][^\n]{1,80})",
            prefix,
        )
        prefix_line_scores = re.findall(r"(?m)^\s*(10(?:[.,]0)?|[0-9](?:[.,][0-9])?)\s*$", prefix)
        rating = nearby_scores[-1] if nearby_scores else (prefix_line_scores[-1] if prefix_line_scores else _rating(prefix))
        if rating is None:
            standalone = re.findall(r"(?m)^\s*(\d+(?:[.,]\d+)?)\s*$", cleaned[max(0, starts[idx] - 500):starts[idx]]) if starts and idx < len(starts) else []
            rating = standalone[-1] if standalone else None
        reviews.append({
            "date": _review_date(context, default_date),
            "author": _author(context, author_hint),
            "source": _source(context, source_hint),
            "text": block,
            "rating": rating,
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
    normalized = _markitdown_text(path)
    return split_review_blocks(normalized or text, default_date, hint, sender, path.name)
