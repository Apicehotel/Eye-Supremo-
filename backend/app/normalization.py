import re
import unicodedata
from decimal import Decimal

UNIT_MAP = {
    "kg": ("kg", Decimal("1")), "kg.": ("kg", Decimal("1")),
    "g": ("kg", Decimal("0.001")), "gr": ("kg", Decimal("0.001")),
    "l": ("l", Decimal("1")), "lt": ("l", Decimal("1")), "ltr": ("l", Decimal("1")),
    "ml": ("l", Decimal("0.001")),
    "pz": ("pz", Decimal("1")), "pezzi": ("pz", Decimal("1")), "pcs": ("pz", Decimal("1")),
    "rotolo": ("rotolo", Decimal("1")), "conf": ("confezione", Decimal("1")),
    "confezione": ("confezione", Decimal("1")), "scatola": ("scatola", Decimal("1")),
    "m": ("m", Decimal("1")), "m2": ("m²", Decimal("1")), "m²": ("m²", Decimal("1")),
    "m3": ("m³", Decimal("1")), "m³": ("m³", Decimal("1")), "paia": ("paio", Decimal("1")),
}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_unit(unit: str | None) -> tuple[str | None, Decimal]:
    if not unit:
        return None, Decimal("1")
    key = unit.strip().lower().replace("mq", "m2").replace("mc", "m3")
    return UNIT_MAP.get(key, (key, Decimal("1")))


def normalized_price(price: Decimal, quantity: Decimal, unit: str | None) -> tuple[str | None, Decimal | None]:
    normalized, factor = normalize_unit(unit)
    base_quantity = quantity * factor
    return normalized, (price / factor if factor else None) if quantity else None
