import re
import unicodedata
from decimal import Decimal

UNIT_MAP = {
    "kg": ("kg", Decimal("1")), "kg.": ("kg", Decimal("1")),
    "kilo": ("kg", Decimal("1")), "kili": ("kg", Decimal("1")), "chilo": ("kg", Decimal("1")), "chili": ("kg", Decimal("1")),
    "g": ("kg", Decimal("0.001")), "gr": ("kg", Decimal("0.001")), "grammo": ("kg", Decimal("0.001")), "grammi": ("kg", Decimal("0.001")),
    "hg": ("kg", Decimal("0.1")), "etto": ("kg", Decimal("0.1")), "etti": ("kg", Decimal("0.1")),
    "l": ("l", Decimal("1")), "lt": ("l", Decimal("1")), "ltr": ("l", Decimal("1")), "litro": ("l", Decimal("1")), "litri": ("l", Decimal("1")),
    "ml": ("l", Decimal("0.001")), "cl": ("l", Decimal("0.01")), "dl": ("l", Decimal("0.1")),
    "pz": ("pz", Decimal("1")), "pezzo": ("pz", Decimal("1")), "pezzi": ("pz", Decimal("1")), "pcs": ("pz", Decimal("1")),
    "pc": ("pz", Decimal("1")), "n": ("pz", Decimal("1")), "nr": ("pz", Decimal("1")), "num": ("pz", Decimal("1")),
    "rotolo": ("rotolo", Decimal("1")), "conf": ("confezione", Decimal("1")),
    "confezione": ("confezione", Decimal("1")), "scatola": ("scatola", Decimal("1")),
    "m": ("m", Decimal("1")), "m2": ("m²", Decimal("1")), "m²": ("m²", Decimal("1")),
    "m3": ("m³", Decimal("1")), "m³": ("m³", Decimal("1")), "paia": ("paio", Decimal("1")),
}

CONTENT_RE = re.compile(
    r"(?P<qty>\d+(?:[.,]\d+|\s+\d+)?)\s*(?P<unit>"
    r"kg|kili|chili|chilo|kilo|grammi|grammo|gr|g|hg|etti|etto|litri|litro|ltr|lt|l|ml|cl|dl|pezzi|pezzo|pcs|pc|pz|n|nr|num"
    r")\b",
    re.IGNORECASE,
)
CONTENT_AFTER_UNIT_RE = re.compile(
    r"(?P<unit>kg|kili|chili|chilo|kilo|grammi|grammo|gr|g|hg|etti|etto|litri|litro|ltr|lt|l|ml|cl|dl)\s*"
    # Package markers may follow immediately, e.g. ``cl50x24``.
    r"(?P<qty>\d+(?:[.,]\d+|\s+\d+)?)(?=\D|$)",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_unit(unit: str | None) -> tuple[str | None, Decimal]:
    if not unit:
        return None, Decimal("1")
    key = unit.strip().lower().replace("mq", "m2").replace("mc", "m3")
    return UNIT_MAP.get(key, (key, Decimal("1")))


def extract_content(description: str) -> tuple[Decimal | None, str | None, Decimal | None]:
    """Estrae un contenuto esplicito dalla descrizione, ad esempio 50g o 1,5L."""
    if not description:
        return None, None, None
    matches = list(CONTENT_RE.finditer(description))
    matches.extend(CONTENT_AFTER_UNIT_RE.finditer(description))
    if not matches:
        return None, None, None
    # In descriptions such as "24 pz ... lt 0 500" the first match is the
    # package count, not the comparable liquid/weight content. Prefer kg/l.
    match = next(
        (candidate for candidate in reversed(matches) if normalize_unit(candidate.group("unit"))[0] in {"kg", "l"}),
        matches[0],
    )
    try:
        quantity = Decimal(match.group("qty").replace(",", ".").replace(" ", "."))
    except Exception:
        return None, None, None
    base, factor = normalize_unit(match.group("unit"))
    if not base:
        return None, None, None
    return quantity, base, quantity * factor


def normalized_price_with_content(
    price: Decimal, quantity: Decimal, unit: str | None, description: str | None
) -> tuple[str | None, Decimal | None]:
    """Normalizza anche confezioni espresse nella descrizione della riga."""
    normalized, factor = normalize_unit(unit)
    if factor and normalized in {"kg", "l"}:
        return normalized, price / factor
    _, content_base, content_in_base = extract_content(description or "")
    if content_in_base and content_in_base > 0 and content_base in {"kg", "l"}:
        if normalized in {"pz", "confezione", "scatola", None} or not unit:
            return content_base, price / content_in_base
    if content_in_base and content_in_base > 0 and content_base == "pz":
        if normalized in {"pz", "confezione", "scatola", None} or not unit:
            return "pz", price / content_in_base
    return normalized, (price / factor if factor else None) if quantity else None


def normalized_price(price: Decimal, quantity: Decimal, unit: str | None) -> tuple[str | None, Decimal | None]:
    normalized, factor = normalize_unit(unit)
    base_quantity = quantity * factor
    return normalized, (price / factor if factor else None) if quantity else None
