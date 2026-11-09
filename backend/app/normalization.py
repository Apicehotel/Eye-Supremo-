"""Normalizzazione di testi, unità e prezzi delle righe fattura.

Il prezzo normalizzato serve a confrontare fornitori: ``€/kg``, ``€/l`` oppure ``€/pz``.
Le descrizioni originali non vengono mai modificate: si legge il contenuto (``500G``,
``KG.1.2``, ``CL.20 X 24``, ``GR.45 PZ.80``) solo per calcolare il prezzo.

Regole principali:

- se l'unità della riga è già kg/l, il prezzo è già per kg/l e la descrizione non conta;
- altrimenti il prezzo è per pezzo o per confezione: si divide per il contenuto letto nella
  descrizione, moltiplicato per il numero di pezzi della confezione (``X24``, ``PZ.80``);
- le unità di misura devono essere parole intere (``MORETTI 66CL`` non contiene «etti»);
- se non si legge nulla di affidabile il prezzo resta quello grezzo, mai un numero inventato.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

UNIT_MAP = {
    "kg": ("kg", Decimal("1")), "kg.": ("kg", Decimal("1")), "k.": ("kg", Decimal("1")), "kgm": ("kg", Decimal("1")),
    "kilo": ("kg", Decimal("1")), "kili": ("kg", Decimal("1")), "chilo": ("kg", Decimal("1")), "chili": ("kg", Decimal("1")),
    "kilogrammi": ("kg", Decimal("1")), "kilogrammo": ("kg", Decimal("1")),
    "g": ("kg", Decimal("0.001")), "gr": ("kg", Decimal("0.001")), "grammo": ("kg", Decimal("0.001")), "grammi": ("kg", Decimal("0.001")),
    "hg": ("kg", Decimal("0.1")), "etto": ("kg", Decimal("0.1")), "etti": ("kg", Decimal("0.1")),
    "l": ("l", Decimal("1")), "lt": ("l", Decimal("1")), "lit": ("l", Decimal("1")), "ltr": ("l", Decimal("1")), "litro": ("l", Decimal("1")), "litri": ("l", Decimal("1")),
    "ml": ("l", Decimal("0.001")), "cl": ("l", Decimal("0.01")), "dl": ("l", Decimal("0.1")),
    # Pezzi
    "pz": ("pz", Decimal("1")), "pezzo": ("pz", Decimal("1")), "pezzi": ("pz", Decimal("1")), "pcs": ("pz", Decimal("1")),
    "pc": ("pz", Decimal("1")), "n": ("pz", Decimal("1")), "n.": ("pz", Decimal("1")), "nr": ("pz", Decimal("1")),
    "num": ("pz", Decimal("1")), "numero": ("pz", Decimal("1")), "un": ("pz", Decimal("1")),
    "cad": ("pz", Decimal("1")), "cadauna": ("pz", Decimal("1")), "cadauno": ("pz", Decimal("1")),
    # Confezioni (il prezzo è per confezione, non per pezzo)
    "rotolo": ("rotolo", Decimal("1")), "conf": ("confezione", Decimal("1")),
    "confezione": ("confezione", Decimal("1")), "scatola": ("scatola", Decimal("1")),
    "ct": ("confezione", Decimal("1")), "cartone": ("confezione", Decimal("1")), "cartoni": ("confezione", Decimal("1")),
    "cf": ("confezione", Decimal("1")), "sc": ("confezione", Decimal("1")), "cs": ("confezione", Decimal("1")),
    "cas": ("confezione", Decimal("1")), "cassa": ("confezione", Decimal("1")), "con": ("confezione", Decimal("1")),
    "cu": ("confezione", Decimal("1")), "bt": ("confezione", Decimal("1")), "pacco": ("confezione", Decimal("1")),
    "sa": ("confezione", Decimal("1")), "bs": ("confezione", Decimal("1")), "busta": ("confezione", Decimal("1")),
    "sacco": ("confezione", Decimal("1")), "rn": ("confezione", Decimal("1")),
    "m": ("m", Decimal("1")), "m2": ("m²", Decimal("1")), "m²": ("m²", Decimal("1")),
    "m3": ("m³", Decimal("1")), "m³": ("m³", Decimal("1")), "paia": ("paio", Decimal("1")),
}

# Unità il cui prezzo è «per pezzo» o «per confezione»: qui il contenuto si legge dalla descrizione.
PIECE_UNITS = frozenset({"pz"})
PACK_UNITS = frozenset({"confezione", "scatola"})

_MASS_VOLUME = r"kg|kili|chili|chilo|kilo|grammi|grammo|gr|g|hg|etti|etto|litri|litro|ltr|lt|lit|l|ml|cl|dl"
# Dopo un numero queste parole indicano un conteggio («G 16 FETTE»): quel numero non è un contenuto.
_COUNT_WORDS = r"pz|pezzi|pcs|fette|filtri|buste|bustine|capsule|cialde|rotoli|fogli|porzioni|bottiglie|lattine|pacchi|barrette"
_TAIL_AFTER_NUMBER_FIRST = r"(?:(?![A-Za-z0-9])(?!\.\d)|(?=[x×]\d))"

# «500G», «1,5 KG», «0.5 litri», «25GX100», «FRUTTA125g»: numero seguito da unità intera.
_NUM_THEN_UNIT = re.compile(
    rf"(?<![0-9])(?P<qty>\d+(?:[.,]\d+)?|0\s\d{{1,3}})\s*(?P<unit>{_MASS_VOLUME}){_TAIL_AFTER_NUMBER_FIRST}",
    re.IGNORECASE,
)
# «KG.1.2», «LT.4», «ML.310», «G1000 X12», «cl 50x24»: unità intera (non dentro una parola) e poi il numero.
_UNIT_THEN_NUM = re.compile(
    rf"(?<![A-Za-z])(?P<unit>{_MASS_VOLUME})\.?\s*(?P<qty>0\s\d{{1,3}}(?!\d)|\d+(?:[.,]\d+)?)(?:(?![0-9A-Za-z])|(?=[x×]\d))",
    re.IGNORECASE,
)
_COUNT_WORD_AFTER = re.compile(rf"^\s*(?:{_COUNT_WORDS})(?![A-Za-z])", re.IGNORECASE)
# Numero di pezzi: «PZ.80», «PZ 48», «PZ. 36», «P.36» (solo con punto e numero), «50PZ», «6PZ240g».
# «PRZ.14» non è un conteggio (porzioni di una torta da 1400 g).
_COUNT_PZ_BEFORE = re.compile(
    rf"(?<![A-Za-z])(?:pz|pezzi|pcs|p(?=\.\s*\d))\.?\s*(?P<n>\d+)(?![0-9])(?![.,]\d)(?!\s*(?:{_MASS_VOLUME})(?![A-Za-z])(?!\.?\s*\d))",
    re.IGNORECASE,
)
_COUNT_PZ_AFTER = re.compile(r"(?<![0-9])(?P<n>\d+)\s*(?:pz|pezzi|pcs)(?![A-Za-z])", re.IGNORECASE)
# «GR.25 PZ.100»: il 25 è un contenuto, non un numero di pezzi.
_UNIT_BEFORE_NUMBER = re.compile(rf"(?<![A-Za-z])(?:{_MASS_VOLUME})\.?\s*$", re.IGNORECASE)
_COUNT_X_RIGHT = re.compile(r"^\s*[x×]\s*(?P<n>\d+)(?![0-9]*[.,]?[0-9]*\s*(?:cm|mm)\b)", re.IGNORECASE)
_COUNT_X_LEFT = re.compile(r"(?<![0-9.,])(?P<n>\d+)\s*[x×]\s*$", re.IGNORECASE)
_MAX_COUNT = 100000
# €/kg o €/l sotto questa soglia: per un articolo da fattura è quasi sempre un errore di interpretazione.
_IMPLAUSIBLY_LOW = Decimal("0.25")
# Sopra questa soglia (es. cartone da «GR.25» senza numero di pezzi) il contenuto letto non è quello della confezione.
_IMPLAUSIBLY_HIGH = Decimal("500")
# Un cartone con un contenuto così piccolo e nessun numero di pezzi indica il peso di un singolo articolo.
_TINY_CONTENT = Decimal("0.1")

_PRECISION = Decimal("0.0001")


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_unit(unit: str | None) -> tuple[str | None, Decimal]:
    if not unit:
        return None, Decimal("1")
    key = unit.strip().lower().replace("mq", "m2").replace("mc", "m3")
    return UNIT_MAP.get(key, (key, Decimal("1")))


@dataclass(frozen=True)
class PackInfo:
    """Cosa si legge nella descrizione: contenuto di una unità e numero di pezzi."""

    content_qty: Decimal | None = None      # come scritto (es. 50 per «50CL»)
    content_base: str | None = None         # «kg» oppure «l»
    content_in_base: Decimal | None = None  # contenuto di una unità, in kg o l
    count: int | None = None                # pezzi nella confezione (es. 24 per «X24»)


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(re.sub(r"\s+", ".", raw.strip()).replace(",", "."))
    except InvalidOperation:
        return None


def _valid_count(value: str) -> int | None:
    try:
        number = int(value)
    except ValueError:
        return None
    return number if 1 <= number <= _MAX_COUNT else None


def parse_pack(description: str | None) -> PackInfo:
    """Legge contenuto e numero di pezzi da una descrizione di fattura."""
    text = (description or "").replace("\n", " ")
    if not text.strip():
        return PackInfo()

    # I marcatori di pezzi (PZ.80, 50PZ) non sono contenuto: si individuano prima e si ignora
    # qualunque unità che cada al loro interno («PZ 48 GR 12» è 48 pezzi da 12 g).
    count_spans: list[tuple[int, int, int]] = []
    for pattern in (_COUNT_PZ_BEFORE, _COUNT_PZ_AFTER):
        for match in pattern.finditer(text):
            if pattern is _COUNT_PZ_AFTER and _UNIT_BEFORE_NUMBER.search(text[: match.start()]):
                continue
            number = _valid_count(match.group("n"))
            if number is not None:
                count_spans.append((match.start(), match.end(), number))

    # «603 LT 1», «6317 GR.50»: se la stessa unità è seguita da un numero, quel numero è il contenuto
    # e quello a sinistra è un codice articolo.
    unit_first_positions = {m.start("unit") for m in _UNIT_THEN_NUM.finditer(text)}

    candidates: list[tuple[int, int, Decimal, str]] = []
    for pattern in (_NUM_THEN_UNIT, _UNIT_THEN_NUM):
        for match in pattern.finditer(text):
            if (
                pattern is _NUM_THEN_UNIT
                and match.start("unit") in unit_first_positions
                and match.start("unit") > match.end("qty")
            ):
                continue
            if any(start <= match.start() < end or start < match.end() <= end for start, end, _ in count_spans):
                continue
            if pattern is _UNIT_THEN_NUM:
                # «285G 16 FETTE»: unità e numero separati da soli spazi e numero seguito da «fette», «pz»…
                # è un conteggio. «GR.25 PZ.100» e «G1000 X12» (uniti) restano contenuto.
                gap = text[match.end("unit"): match.start("qty")]
                if gap and not gap.strip() and _COUNT_WORD_AFTER.search(text[match.end():]):
                    continue
            quantity = _to_decimal(match.group("qty"))
            base, factor = normalize_unit(match.group("unit"))
            if quantity is None or quantity <= 0 or base not in {"kg", "l"}:
                continue
            candidates.append((match.start(), match.end(), quantity, match.group("unit")))
    if not candidates:
        count = count_spans[0][2] if count_spans else None
        return PackInfo(count=count)

    start, end, quantity, unit = min(candidates, key=lambda item: item[0])
    base, factor = normalize_unit(unit)
    count: int | None = None
    right = _COUNT_X_RIGHT.search(text[end:])
    if right:
        count = _valid_count(right.group("n"))
    if count is None:
        left = _COUNT_X_LEFT.search(text[:start])
        if left:
            count = _valid_count(left.group("n"))
    if count is None and count_spans:
        count = count_spans[0][2]
    return PackInfo(quantity, base, quantity * factor, count)


def extract_content(description: str) -> tuple[Decimal | None, str | None, Decimal | None]:
    """Contenuto di una singola unità, ad esempio ``50g`` o ``1,5L``.

    Se manca un contenuto in kg/l ma c'è un numero di pezzi (``24 pz``), restituisce quello come ``pz``.
    """
    if not description:
        return None, None, None
    info = parse_pack(description)
    if info.content_in_base is not None:
        return info.content_qty, info.content_base, info.content_in_base
    if info.count is not None:
        count = Decimal(info.count)
        return count, "pz", count
    return None, None, None


@dataclass(frozen=True)
class PriceNormalization:
    unit: str | None
    price: Decimal | None
    # unit: già al kg/l | content: diviso per contenuto | count: diviso per pezzi | raw: invariato
    basis: str = "raw"
    # Quanti kg/l/pz stanno in una unità fatturata: quantità normalizzata = quantità × questo valore.
    base_per_unit: Decimal = Decimal("1")
    # True se «pezzo» potrebbe essere un singolo articolo o l'intera confezione (stima con la quantità).
    ambiguous: bool = False


def _round(value: Decimal) -> Decimal:
    return value.quantize(_PRECISION, rounding=ROUND_HALF_UP)


def normalize_row_price(price: Decimal, quantity: Decimal, unit: str | None, description: str | None) -> PriceNormalization:
    """Prezzo confrontabile di una riga: €/kg, €/l o €/pz quando è possibile, altrimenti invariato."""
    price = Decimal(price)
    quantity = Decimal(quantity or 0)
    base, factor = normalize_unit(unit)
    raw = PriceNormalization(base, (price / factor) if factor else None, "raw")
    if price <= 0:
        return raw
    # Il prezzo è già per kg/l: la descrizione non cambia nulla.
    if factor and base in {"kg", "l"}:
        per_base = price / factor
        # «ML»/«G» con prezzo da pezzo (es. 455.240 €/l): unità frazionaria usata male, non è un prezzo al litro.
        if factor < 1 and per_base > _IMPLAUSIBLY_HIGH:
            return raw
        return PriceNormalization(base, _round(per_base), "unit", factor)
    # Unità di misura estranea (ore, mc, kWh, metri…): nessun contenuto da cercare.
    if base is not None and base not in PIECE_UNITS and base not in PACK_UNITS:
        return raw

    info = parse_pack(description)
    piece = base in PIECE_UNITS
    count = info.count if info.count and info.count > 1 else None

    if info.content_in_base is not None and info.content_in_base > 0:
        per_unit = info.content_in_base
        ambiguous = False
        if count:
            # «32GX32» venduto a pezzi (quantità = 32): il prezzo è del singolo; altrimenti è della confezione.
            if piece and quantity == count:
                pass
            else:
                per_unit = info.content_in_base * count
                if piece:
                    ambiguous = True
                    # Un prezzo sotto la soglia come confezione ma credibile come singolo (es. un bicchiere
                    # da 0,081 € indicato «120 ml CONF.50 pz») è quasi sempre il prezzo del singolo.
                    if price / per_unit < _IMPLAUSIBLY_LOW and price / info.content_in_base >= _IMPLAUSIBLY_LOW:
                        per_unit = info.content_in_base
        if base in PACK_UNITS and not count and info.content_in_base < _TINY_CONTENT:
            return raw
        normalized = price / per_unit
        if normalized > _IMPLAUSIBLY_HIGH:
            return raw
        return PriceNormalization(info.content_base, _round(normalized), "content", per_unit, ambiguous)

    # Solo il numero di pezzi: ha senso per confezioni/cartoni, non per un «pezzo» già singolo.
    if count and not piece:
        return PriceNormalization("pz", _round(price / Decimal(count)), "count", Decimal(count))
    return raw


def normalized_price_with_content(
    price: Decimal, quantity: Decimal, unit: str | None, description: str | None
) -> tuple[str | None, Decimal | None]:
    """Normalizza anche confezioni espresse nella descrizione della riga."""
    result = normalize_row_price(price, quantity, unit, description)
    return result.unit, result.price


def normalized_price(price: Decimal, quantity: Decimal, unit: str | None) -> tuple[str | None, Decimal | None]:
    normalized, factor = normalize_unit(unit)
    base_quantity = quantity * factor
    return normalized, (price / factor if factor else None) if quantity else None


def fill_normalized_price(row: dict, description: str | None = None) -> dict:
    """Completa ``normalized_price``/``normalized_unit`` in una riga centrale che ne è priva.

    Il centrale (Supabase) conserva solo il prezzo grezzo: qui si calcola in lettura, senza scrivere
    nulla. Una riga che ha già un prezzo normalizzato non viene toccata.
    """
    current = row.get("normalized_price")
    if current not in (None, 0, "0"):
        return row
    try:
        price = Decimal(str(row.get("unit_price")))
        quantity = Decimal(str(row.get("quantity") if row.get("quantity") is not None else 1))
    except InvalidOperation:
        return row
    text = description or row.get("original_description") or row.get("normalized_description")
    result = normalize_row_price(price, quantity, row.get("original_unit"), text)
    if result.price is None or result.basis == "raw":
        return row
    row["normalized_price"] = float(result.price)
    row["normalized_unit"] = result.unit
    row["normalization_basis"] = result.basis
    return row
