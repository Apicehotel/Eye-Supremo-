"""Gusto e grammatura di una variante prodotto, anche con diciture abbreviate.

Serve a elencare tutte le varianti di una famiglia (es. «marmellata») in ordine
di gusto e di grammatura, qualunque sia la dicitura del fornitore
(«MARM. ARANCE 25GX100», «CONFET ALBIC 650 GR», «confettura extra fragole»).
Non modifica mai le descrizioni originali: calcola solo etichette di lettura.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .normalization import normalize_text

# Gusto canonico -> forme che compaiono in fattura (parole intere o abbreviazioni).
# Si confronta la parola intera: le abbreviazioni sono elencate una per una (prese dal catalogo reale).
FLAVORS: dict[str, tuple[str, ...]] = {
    "arancia": ("arancia", "arance", "aranc", "arancio"),
    "fragola": ("fragola", "fragole", "frag"),
    "albicocca": ("albicocca", "albicocche", "albic", "albicoc"),
    "ciliegia": ("ciliegia", "ciliegie", "cilieg"),
    "amarena": ("amarena", "amarene", "visciola", "visciole", "visciolata"),
    "pesca": ("pesca", "pesche", "pesch"),
    "mirtillo": ("mirtillo", "mirtilli", "mirt"),
    "lampone": ("lampone", "lamponi"),
    "mora": ("mora", "more"),
    "prugna": ("prugna", "prugne", "prugn", "susina", "susine"),
    "pera": ("pera", "pere"),
    "mela": ("mela", "mele", "cotogna", "cotogne"),
    "fico": ("fico", "fichi"),
    "limone": ("limone", "limoni", "limon"),
    "pomodoro": ("pomodoro", "pomodori", "pomod"),
    "sambuco": ("sambuco",),
    "ananas": ("ananas",),
    "cioccolato": ("cioccolato", "cioccolata", "ciocc", "cioc", "cioco", "choco", "chocolate"),
    "nocciola": ("nocciola", "nocciole", "nocc", "gianduia"),
    "pistacchio": ("pistacchio", "pistacchi", "pist"),
    "crema": ("crema",),
    "miele": ("miele",),
}

# Espressioni di più parole (controllate sul testo intero).
FLAVOR_PHRASES: dict[str, tuple[str, ...]] = {
    "frutti di bosco": ("frutti di bosco", "frutti bosco", "frutta di bosco", "frut bosco", "fr bosco", "f bosco", "bosco"),
}

_NUMBER = r"\d+(?:[ ,.]\d{1,3})?"
_AFTER = re.compile(rf"(?<![a-z0-9])(?:\d+\s*x\s*)?(?P<n>{_NUMBER})\s*(?P<u>kg|gr|g|ml|cl|lt|l)(?:(?![a-z])|(?=x\d))")
_BEFORE = re.compile(rf"(?<![a-z])(?P<u>kg|gr|g|ml|cl|lt|l)\s*(?P<n>{_NUMBER})(?![0-9a-z])")
_UNIT_FACTOR = {"kg": (1000, "g"), "gr": (1, "g"), "g": (1, "g"), "ml": (1, "ml"), "cl": (10, "ml"), "lt": (1000, "ml"), "l": (1000, "ml")}


def _to_decimal(raw: str, unit: str) -> Decimal | None:
    raw = raw.strip()
    # «1 5 l», «0 24 kg», «1,9 kg»: la parte decimale è separata da spazio o virgola solo per kg/l.
    if unit in {"kg", "l", "lt"}:
        raw = re.sub(r"[ ,]", ".", raw)
    else:
        raw = re.sub(r"[ .,]", "", raw)
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def grammage(name: str) -> dict | None:
    """Contenuto di una singola unità: ``{"value": 650.0, "unit": "g", "label": "650 g"}``.

    ``120x25g`` e ``25gx100`` valgono 25 g (peso della singola porzione, non il numero di pezzi).
    """
    text = normalize_text(name or "")
    if not text:
        return None
    hits = []
    for pattern in (_AFTER, _BEFORE):
        for match in pattern.finditer(text):
            unit = match.group("u")
            value = _to_decimal(match.group("n"), unit)
            if value is None or value <= 0:
                continue
            factor, base = _UNIT_FACTOR[unit]
            hits.append((match.start(), float(value * factor), base))
    if not hits:
        return None
    _, amount, base = min(hits, key=lambda item: item[0])
    return {"value": amount, "unit": base, "label": _label(amount, base)}


def _label(amount: float, base: str) -> str:
    if base == "g":
        return f"{amount / 1000:g} kg".replace(".", ",") if amount >= 1000 else f"{amount:g} g"
    return f"{amount / 1000:g} l".replace(".", ",") if amount >= 1000 else f"{amount:g} ml"


def flavors(name: str) -> list[str]:
    """Gusti riconosciuti nella descrizione, nell'ordine in cui compaiono."""
    text = normalize_text(name or "")
    if not text:
        return []
    found: list[tuple[int, str]] = []
    padded = f" {text} "
    for label, forms in FLAVOR_PHRASES.items():
        positions = [padded.find(f" {form} ") for form in forms if f" {form} " in padded]
        if positions:
            found.append((min(positions), label))
    words = text.split()
    for index, word in enumerate(words):
        for label, forms in FLAVORS.items():
            if word in forms:
                found.append((padded.find(f" {word} "), label))
                break
    ordered: list[str] = []
    for _, label in sorted(found, key=lambda item: item[0]):
        if label not in ordered:
            ordered.append(label)
    return ordered


def variant_info(name: str) -> dict:
    content = grammage(name)
    tastes = flavors(name)
    return {
        "flavor": " + ".join(tastes) if tastes else None,
        "content_label": content["label"] if content else None,
        "content_value": content["value"] if content else None,
        "content_unit": content["unit"] if content else None,
    }


def annotate_variants(items: list[dict], *, name_key: str = "nome_canonico") -> list[dict]:
    """Aggiunge gusto e grammatura a ogni voce, senza toccare gli altri campi."""
    for item in items:
        if isinstance(item, dict):
            item.update(variant_info(str(item.get(name_key) or item.get("canonical_name") or "")))
    return items


def sort_variants(items: list[dict], *, name_key: str = "nome_canonico") -> list[dict]:
    """Ordina per gusto, poi per grammatura crescente, poi per nome.

    Si applica solo se almeno due voci hanno un gusto: per gli altri prodotti l'ordine resta quello di partenza.
    """
    if sum(1 for item in items if isinstance(item, dict) and item.get("flavor")) < 2:
        return items

    def key(item: dict):
        flavor = item.get("flavor") or "~"
        value = item.get("content_value")
        return (flavor, value is None, value or 0.0, str(item.get(name_key) or item.get("canonical_name") or ""))

    return sorted(items, key=key)
