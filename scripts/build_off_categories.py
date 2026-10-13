"""Genera backend/app/data/off_categories_it.json dalla tassonomia categorie di Open Food Facts.

Fonte: https://github.com/openfoodfacts/openfoodfacts-server (taxonomies/food/categories.txt).
Dati sotto licenza ODbL: https://opendatacommons.org/licenses/odbl/ - attribuzione: «Open Food Facts».
Uso:  python scripts/build_off_categories.py
Rieseguibile in qualsiasi momento per aggiornare il dizionario (richiede Internet).
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/openfoodfacts/openfoodfacts-server/main/taxonomies/food/categories.txt"
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "off_categories_it.json"


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text)).strip()


def parse(raw: str) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for block in raw.split("\n\n"):
        parents: list[str] = []
        en: list[str] = []
        it: list[str] = []
        for line in block.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("<"):
                parents.append(re.sub(r"^en:\s*", "en:", line.lstrip("< ").strip()))
            elif line.startswith("en:") and not en:
                en = [x.strip() for x in line[3:].split(",") if x.strip()]
            elif line.startswith("it:"):
                it = [x.strip() for x in line[3:].split(",") if x.strip()]
        if en:
            entries[f"en:{en[0]}"] = {"parents": parents, "it": it}
    return entries


# Macro-categorie in linguaggio quotidiano. Si assegna la prima regola che trova uno degli antenati
# (nomi inglesi della tassonomia) elencati: l'ordine conta.
MACRO_RULES: list[tuple[str, set[str]]] = [
    ("Alcolici", {"Alcoholic beverages", "Wines", "Beers", "Spirits"}),
    ("Caffè e tè", {"Coffees", "Teas", "Herbal teas", "Instant coffees", "Coffee capsules", "Tea bags"}),
    ("Bevande", {"Beverages", "Beverages and beverages preparations", "Waters", "Fruit juices", "Sodas"}),
    ("Uova", {"Eggs and their products", "Eggs"}),
    ("Latticini e formaggi", {"Dairies", "Cheeses", "Milks", "Butters", "Creams"}),
    ("Carne e salumi", {"Meats and their products", "Meats", "Prepared meats", "Charcuteries"}),
    ("Pesce", {"Seafood", "Fishes", "Fishes and their products"}),
    ("Verdura e ortaggi", {"Vegetables", "Vegetables based foods", "Mushrooms"}),
    ("Frutta", {"Fruits", "Fruit-based foods", "Nuts"}),
    ("Dolci e pasticceria", {"Sweet snacks", "Desserts", "Biscuits and crackers", "Cocoa and its products", "Sweet pastries and pies", "Viennoiseries", "Honeys", "Bee products", "Sweeteners", "Spreads"}),
    ("Pane e pizze", {"Breads", "Pizzas pies and quiches", "Breadsticks"}),
    ("Pasta, riso e cereali", {"Pastas", "Pastas and dumplings", "Cereals and their products", "Cereals and potatoes", "Rices", "Breakfast cereals"}),
    ("Oli e grassi", {"Fats", "Olive oils", "Olive tree products", "Vegetable oils"}),
    ("Condimenti e salse", {"Condiments", "Sauces", "Spices", "Vinegars", "Salts"}),
    ("Surgelati", {"Frozen foods"}),
]


def macro_for(ancestor_names: list[str]) -> str:
    names = set(ancestor_names)
    for macro, needles in MACRO_RULES:
        if names & needles:
            return macro
    return "Altri alimentari"


def main() -> int:
    raw = urllib.request.urlopen(URL, timeout=120).read().decode("utf8")
    entries = parse(raw)

    def chain(key: str) -> list[str]:
        out, seen = [key], {key}
        while entries.get(out[-1], {}).get("parents"):
            nxt = entries[out[-1]]["parents"][0]
            nxt = nxt if nxt.startswith("en:") else f"en:{nxt}"
            if nxt in seen or nxt not in entries:
                break
            out.append(nxt)
            seen.add(nxt)
        return out  # dal più specifico alla radice

    def label(key: str) -> str | None:
        names = entries.get(key, {}).get("it") or []
        return names[0] if names else None

    result: dict[str, dict] = {}
    for key, entry in entries.items():
        names = entry["it"]
        if not names:
            continue
        ancestors = chain(key)
        macro = macro_for([k[3:] for k in ancestors])
        for synonym in names:
            n = norm(synonym)
            if len(n) < 3:
                continue
            prev = result.get(n)
            if prev and prev["depth"] >= len(ancestors):
                continue
            result[n] = {"label": names[0], "macro": macro, "depth": len(ancestors)}
    OUT.write_text(json.dumps({"source": "Open Food Facts (ODbL)", "categories": result}, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    print(f"{len(result)} sinonimi italiani → {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
