"""Deterministic, dependency-free ranking for invoice product descriptions.

This module never invents products: it only scores existing invoice rows.
Use it after database retrieval, not as a replacement for access controls.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

FILLERS = frozenset("trova cercami cerca mostrami mostra prodotto prodotti articolo articoli fattura fatture quanto costa prezzo del della di il la lo un una per".split())
UNIT_TOKENS = frozenset(("kg", "g", "gr", "lt", "l", "ml", "pz", "conf", "confezione"))


def tokens(value: str) -> tuple[str, ...]:
    ascii_text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    return tuple(t for t in re.findall(r"[a-z0-9]+", ascii_text) if t not in FILLERS)


def product_score(query: str, description: str, *, code: str | None = None) -> float:
    """Return a score between 0 and 1. Codes match as whole tokens only."""
    q = tokens(query)
    d = tokens(description)
    if not q or not d:
        return 0.0
    qset, dset = set(q), set(d)
    if code and set(tokens(code)) & qset:
        return 1.0
    exact = len(qset & dset) / len(qset)
    soft = sum(max((SequenceMatcher(None, t, x).ratio() for x in dset), default=0.0) for t in qset) / len(qset)
    # Numeric identifiers and pack sizes must not be approximated.
    numeric = {t for t in qset if t.isdigit()}
    if numeric and not numeric.issubset(dset):
        return 0.0
    return round(0.8 * exact + 0.2 * soft, 4)


def rank_products(query: str, products: list[dict], *, threshold: float = 0.55) -> list[dict]:
    """Rank existing records without changing the source objects."""
    ranked = []
    for product in products:
        score = product_score(query, str(product.get("description") or ""), code=product.get("code"))
        if score >= threshold:
            ranked.append({**product, "match_score": score})
    return sorted(ranked, key=lambda item: (-item["match_score"], str(item.get("description", ""))))
