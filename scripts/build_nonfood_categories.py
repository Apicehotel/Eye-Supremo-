"""Genera backend/app/data/off_nonfood_it.json dalle tassonomie NON alimentari di Open Food Facts.

Fonti (repo openfoodfacts-server): taxonomies/product/categories.txt (Open Products Facts) e
taxonomies/beauty/categories.txt (Open Beauty Facts). Dati ODbL, attribuzione «Open Food Facts».
Uso:  python scripts/build_nonfood_categories.py   (richiede Internet)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_off_categories import norm, parse  # noqa: E402

BASE = "https://raw.githubusercontent.com/openfoodfacts/openfoodfacts-server/main/taxonomies/"
SOURCES = ["product/categories.txt", "beauty/categories.txt"]
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "off_nonfood_it.json"

# Radice (nome inglese) → famiglia in linguaggio quotidiano. Le radici non elencate sono scartate.
FAMILY_BY_ROOT = {
    "Household chemicals": "Pulizia e igiene", "Hygiene": "Pulizia e igiene", "Shaving": "Pulizia e igiene", "Body": "Pulizia e igiene",
    "Face": "Pulizia e igiene", "Hair": "Pulizia e igiene", "Suncare": "Pulizia e igiene", "Perfumes": "Pulizia e igiene",
    "Health & Beauty": "Pulizia e igiene", "Accessories": "Pulizia e igiene", "Cotton buds": "Pulizia e igiene", "Papers": "Carta e cancelleria",
    "Hardware": "Materiali e attrezzature", "Adhesives & Sealants": "Materiali e attrezzature", "Business & Industrial": "Materiali e attrezzature",
    "Home & Garden": "Casa e arredo", "Furniture": "Casa e arredo", "Electronics": "Elettronica e informatica", "Software": "Elettronica e informatica",
    "Office Supplies": "Carta e cancelleria", "Media": "Carta e cancelleria", "Tobacco Products": "Tabacchi", "Baby & Toddler": "Infanzia",
    "Animals & Pet Supplies": "Animali", "Luggage & Bags": "Bagagli e borse", "Apparel & Accessories": "Abbigliamento e tessili",
    "Toys & Games": "Giochi e tempo libero", "Sporting Goods": "Giochi e tempo libero", "Arts & Entertainment": "Giochi e tempo libero",
}


def main() -> int:
    result: dict[str, dict] = {}
    for src in SOURCES:
        entries = parse(urllib.request.urlopen(BASE + src, timeout=120).read().decode("utf8"))

        def root(key: str) -> tuple[str, int]:
            seen, depth = {key}, 1
            while entries[key]["parents"]:
                nxt = entries[key]["parents"][0]
                nxt = nxt if nxt.startswith("en:") else f"en:{nxt}"
                if nxt in seen or nxt not in entries:
                    break
                key = nxt
                seen.add(key)
                depth += 1
            return key[3:], depth

        for key, entry in entries.items():
            family = FAMILY_BY_ROOT.get(root(key)[0])
            if not family or not entry["it"]:
                continue
            depth = root(key)[1]
            for synonym in entry["it"]:
                n = norm(synonym)
                if len(n) < 4:
                    continue
                prev = result.get(n)
                if prev and prev["depth"] >= depth:
                    continue
                result[n] = {"label": entry["it"][0], "family": family, "depth": depth}
    OUT.write_text(json.dumps({"source": "Open Food Facts (ODbL)", "categories": result}, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    print(f"{len(result)} sinonimi non alimentari → {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
