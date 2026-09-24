"""Normalizzazione unità/prezzo e filtro righe inutili per Ask Fatture."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

# Unità → (base, fattore verso base). es. 1 g = 0.001 kg
UNIT_TO_BASE: dict[str, tuple[str, Decimal]] = {
    "kg": ("kg", Decimal("1")),
    "kg.": ("kg", Decimal("1")),
    "kilo": ("kg", Decimal("1")),
    "kili": ("kg", Decimal("1")),
    "chili": ("kg", Decimal("1")),
    "chilo": ("kg", Decimal("1")),
    "g": ("kg", Decimal("0.001")),
    "gr": ("kg", Decimal("0.001")),
    "grammi": ("kg", Decimal("0.001")),
    "grammo": ("kg", Decimal("0.001")),
    "hg": ("kg", Decimal("0.1")),
    "etto": ("kg", Decimal("0.1")),
    "etti": ("kg", Decimal("0.1")),
    "l": ("l", Decimal("1")),
    "lt": ("l", Decimal("1")),
    "ltr": ("l", Decimal("1")),
    "litro": ("l", Decimal("1")),
    "litri": ("l", Decimal("1")),
    "ml": ("l", Decimal("0.001")),
    "cl": ("l", Decimal("0.01")),
    "dl": ("l", Decimal("0.1")),
    "pz": ("pz", Decimal("1")),
    "pezzo": ("pz", Decimal("1")),
    "pezzi": ("pz", Decimal("1")),
    "pcs": ("pz", Decimal("1")),
    "pc": ("pz", Decimal("1")),
    "n": ("pz", Decimal("1")),
    "nr": ("pz", Decimal("1")),
    "num": ("pz", Decimal("1")),
    "conf": ("confezione", Decimal("1")),
    "confezione": ("confezione", Decimal("1")),
    "ct": ("confezione", Decimal("1")),
    "scatola": ("scatola", Decimal("1")),
    "scat": ("scatola", Decimal("1")),
}

# Contenuto: "3 kg", "50g", "1,5L", "5LT", "750 ml", "2 etti", "75cl"
CONTENT_RE = re.compile(
    r"(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>"
    r"kg|kili|chili|chilo|kilo|"
    r"grammi|grammo|gr|g|"
    r"hg|etti|etto|"
    r"litri|litro|ltr|lt|l|"
    r"ml|cl|dl"
    r")\b",
    re.IGNORECASE,
)

# Righe da NON archiviare (rumore contabile / non prodotto)
NOISE_PATTERNS = [
    r"\bcarburante\b",
    r"\bgasolio\b",
    r"\bbenzina\b",
    r"\bad[\s-]?blue\b",
    r"\bsconto\b",
    r"\bsconti\b",
    r"\babbuono\b",
    r"\barrotondament",
    r"\bbollo\b",
    r"\bmarca\s+da\s+bollo\b",
    r"\bspese\s+di\s+trasporto\b",
    r"\bspese\s+trasporto\b",
    r"\bporto\s+franco\b",
    r"\bcontributo\s+conai\b",
    r"\bconai\b",
    r"\bomaggio\b",
    r"\brivalsa\b",
    r"\bcassa\s+prev",
    r"\banticipo\b",
    r"\bacconto\b",
    r"\bdeposito\s+cauzionale\b",
    r"\bcontrassegno\b",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)


def _dec(value: float | str | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def is_noise_line(description: str) -> bool:
    """True se la riga non è un prodotto utile (carburante, sconti, bollati…)."""
    if not description or not description.strip():
        return True
    return bool(NOISE_RE.search(description))


def lookup_unit(unit: str | None) -> tuple[str | None, Decimal]:
    if not unit:
        return None, Decimal("1")
    key = unit.strip().lower().replace("mq", "m2").replace("mc", "m3")
    key = key.replace(".", "")
    return UNIT_TO_BASE.get(key, (key, Decimal("1")))


def extract_content(description: str) -> tuple[Decimal | None, str | None, Decimal | None]:
    """
    Estrae contenuto dalla descrizione.
    Ritorna (quantità_contenuto, unità_base, quantità_in_unità_base).
    Es. "BOMBOLONE 3 KG" → (3, "kg", 3)
         "CONF 50G" → (50, "kg", 0.05)
         "2 etti" → (2, "kg", 0.2)
    """
    if not description:
        return None, None, None
    match = CONTENT_RE.search(description)
    if not match:
        return None, None, None
    qty = _dec(match.group("qty"))
    raw_unit = match.group("unit")
    base, factor = lookup_unit(raw_unit)
    if qty is None or not base:
        return None, None, None
    return qty, base, qty * factor


def normalize_line(
    *,
    description: str,
    quantita: float | None,
    unita: str | None,
    prezzo_unitario: float | None,
    totale_riga: float | None = None,
    known_pack: dict | None = None,
) -> dict:
    """
    Calcola prezzo dichiarato (unitario in fattura) e prezzo normalizzato confrontabile.

    Regole (peso e litri allo stesso modo):
    - UM g/kg → €/kg; UM ml/cl/dl/lt/l → €/l
    - UM pz/conf + contenuto in descrizione OPPURE pack noto a catalogo (inserito da Riona/cucina):
      prezzo_normalizzato = prezzo_unitario / contenuto_in_base
    - Solo pezzo senza contenuto: normalizzato = prezzo_unitario in €/pz.

    known_pack: {"contenuto": 50, "unita": "g"} oppure già {"contenuto_base": 0.05, "base": "kg"}
    """
    noise = is_noise_line(description)
    qty = _dec(quantita) or Decimal("1")
    price = _dec(prezzo_unitario)
    um_base, um_factor = lookup_unit(unita)
    content_qty, content_base, content_in_base = extract_content(description)
    pack_source = "descrizione" if content_in_base else None

    # Pack manuale da catalogo prodotto (se la fattura non dice i grammi/litri del pezzo)
    if content_in_base is None and known_pack:
        if known_pack.get("contenuto_base") and known_pack.get("base"):
            content_in_base = _dec(known_pack["contenuto_base"])
            content_base = known_pack.get("base")
            content_qty = _dec(known_pack.get("contenuto")) or content_in_base
            pack_source = "catalogo"
        elif known_pack.get("contenuto") and known_pack.get("unita"):
            content_qty = _dec(known_pack["contenuto"])
            content_base, factor = lookup_unit(str(known_pack["unita"]))
            if content_qty is not None and content_base and factor:
                content_in_base = content_qty * factor
                pack_source = "catalogo"

    piece_units = {"pz", "confezione", "scatola"}

    prezzo_norm: Decimal | None = None
    unita_norm: str | None = um_base
    note = ""
    pezzi_stimati: float | None = None

    if price is not None and um_base in {"kg", "l"} and um_factor != 0:
        prezzo_norm = price / um_factor
        unita_norm = um_base
        note = f"unitario {unita or um_base} → €/{um_base}"
        # Se conosciamo il pezzo (es. bombolone 200g) e la riga è in kg, stima i pezzi
        if content_in_base and content_in_base > 0 and content_base == um_base:
            # qty è in unità di fattura (es. 40 kg); porta a base
            qty_base = qty * um_factor
            pezzi_stimati = float(qty_base / content_in_base)
            note += f" · ~{pezzi_stimati:.0f} pezzi da pack"
    elif (
        price is not None
        and content_in_base
        and content_in_base > 0
        and content_base in {"kg", "l"}
        and (um_base in piece_units or um_base is None or um_base not in {"kg", "l"})
    ):
        prezzo_norm = price / content_in_base
        unita_norm = content_base
        note = f"unitario/pz su pack ({pack_source}) → €/{content_base}"
    elif price is not None and (um_base in piece_units or um_base is None):
        prezzo_norm = price
        unita_norm = "pz"
        note = "prezzo unitario €/pz (pack sconosciuto: inseriscilo a catalogo)"
    elif price is not None:
        prezzo_norm = price
        unita_norm = um_base or (unita.lower() if unita else "pz")
        note = "senza conversione"

    return {
        "descrizione": description,
        "descrizione_norm": normalize_text(description),
        "quantita": float(qty) if qty is not None else None,
        "unita": unita,
        "unita_normalizzata": unita_norm,
        "prezzo_unitario": float(price) if price is not None else None,
        "prezzo_normalizzato": float(prezzo_norm) if prezzo_norm is not None else None,
        "contenuto_base": float(content_in_base) if content_in_base is not None else None,
        "pezzi_stimati": pezzi_stimati,
        "pack_source": pack_source,
        "totale_riga": totale_riga,
        "is_noise": noise,
        "norm_note": note,
    }
