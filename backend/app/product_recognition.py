"""Riconoscimento prodotto da una descrizione di riga fattura.

Fonti:
- Open Food Facts (tassonomia categorie in italiano, ODbL): prodotto specifico + macro-categoria.
  Dizionario offline in ``data/off_categories_it.json`` (rigenerabile con ``scripts/build_off_categories.py``).
- Marche e famiglie non alimentari: elenchi ricavati dalle fatture reali dell'archivio.
Nessuna chiamata di rete: il riconoscimento è locale e istantaneo.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .normalization import normalize_text

DATA_FILE = Path(__file__).parent / "data" / "off_categories_it.json"
NONFOOD_FILE = Path(__file__).parent / "data" / "off_nonfood_it.json"

# Marche trovate nelle fatture (chiave normalizzata → nome mostrato). Si estende senza toccare il resto.
BRANDS: dict[str, str] = {
    "grifo": "Grifo", "grifolatte": "Grifo", "colfiorito": "Colfiorito", "fyffes": "Fyffes", "chiquita": "Chiquita",
    "coca cola": "Coca-Cola", "twinings": "Twinings", "twining": "Twinings", "melinda": "Melinda", "pukka": "Pukka",
    "schar": "Schär", "sterilgarda": "Sterilgarda", "san pellegrino": "San Pellegrino", "sanpellegrino": "San Pellegrino",
    "schweppes": "Schweppes", "nutella": "Nutella", "perugina": "Perugina", "nescafe": "Nescafé", "nestle": "Nestlé",
    "valsoia": "Valsoia", "aperol": "Aperol", "delifrance": "Delifrance", "pompadour": "Pompadour", "nutrifree": "Nutrifree",
    "venosta": "Valvenosta", "barilla": "Barilla", "ferrero": "Ferrero", "lavazza": "Lavazza", "illy": "illy",
    "tullia": "Tullia", "lilia": "Lilia", "san benedetto": "San Benedetto", "arco": "Arco", "la colonica": "La Colonica",
    "xugia": "Xugia", "otello": "Otello", "gargani": "Gargani", "camillo": "Camillo", "treco": "Treco", "lucart": "Lucart",
    "sanikal": "Sanikal", "montenegro": "Montenegro", "ichnusa": "Ichnusa", "nastro azzurro": "Nastro Azzurro", "bel paese": "Bel Paese",
    "galbani": "Galbani", "trevalli": "Trevalli", "brunico": "Latteria Brunico", "amica chips": "Amica Chips", "scarlino": "Scarlino",
    "exquisa": "Exquisa", "granarolo": "Granarolo", "fiorone": "Fiorone", "orsero": "Orsero", "cuoko": "Cuoko", "bonchef": "Bonchef",
}

# Righe che non sono cibo: parole (normalizzate) → famiglia.
NON_FOOD: list[tuple[str, set[str]]] = [
    ("Accessori e ricambi", {"molla", "molle", "portacarta", "portarotolo", "portasapone", "dispenser", "portascopino", "scopino", "dosatore", "dosatori"}),
    ("Energia e utenze", {"energia", "gasolio", "potenza", "dispacciamento", "cogenerazione", "rinnovabili", "contatore", "acquedotto",
                           "fognatura", "depurazione", "perequazione", "oneri", "perdite di rete", "quota fissa", "quota energia",
                           "fascia", "gas naturale", "elettrica", "tariffa", "ricalcolo", "ricalcoli", "scaglione"}),
    ("Lavanderia e biancheria a noleggio", {"lavanolo", "lavaggio", "lavata", "stirata", "piumone", "piumino", "trapunta", "scendibagno",
                                             "accappatoio", "asciugamano", "federa", "lenzuolo", "lenzuola", "coprimacchia", "tovagliolo",
                                             "tovaglia", "telo", "tappeto", "torcione", "coperta", "coperte"}),
    ("Imposte e voci contabili", {"imposte", "imposta", "accisa", "arrotondamento", "sconto", "omaggio", "addebito", "accredito",
                                   "autofattura", "reverse", "cauzioni", "interessi", "imponibile", "ristorno", "iva", "bollo",
                                   "commissioni", "commissione", "rapporto", "documento", "riga ausiliaria", "conai", "spese", "incasso", "rivalsa",
                                   "arrotondamenti", "dest", "destinazione", "oggetto", "iban", "quota", "contributo", "diritti",
                                   "corrispettivo", "ricarica", "ricariche", "affitto", "pasto", "pasti", "camera", "pernottamento"}),
    ("Servizi e manutenzione", {"riparazione", "intervento", "manutenzione", "installazione", "noleggio", "assistenza", "canone",
                                 "trasporto", "spedizione", "pernottamento", "consegna", "manodopera", "sostituzione", "servizio",
                                 "servizi", "prestazione", "lavoro", "lavori", "pulizia", "consulenza", "software"}),
    ("Pulizia e igiene", {"detergente", "candeggina", "sgrassatore", "sgrassato", "guanti", "sapone", "doccia", "bidet", "carta igienica", "saponetta", "saponette",
                           "igienica", "asciugamano", "spray", "detersivo", "lavatrice"}),
    ("Monouso e tavola", {"bicchiere", "piatto", "piatti", "posate", "vassoio", "tnt", "pantofola", "veline", "velina"}),
    ("Materiali e attrezzature", {"tubo", "cavo", "vite", "viti", "ottone", "inox", "lampadina", "lampada", "guarnizione", "bobina",
                                   "cazzuola", "nastro adesivo", "bottone", "bottoni", "impianto", "ricambio", "silicone", "cartoncino",
                                   "stampa", "shopper", "busta", "scatola", "sacchi", "sacco"}),
]

# Prodotti tipici che Open Food Facts non ha (o ha con nomi diversi): (stem, macro-categoria, etichetta).
# Stem ≥ 6 lettere = «contenuto nella parola» (minibomboloni); più corti = «inizia con».
EXTRA_FOODS: list[tuple[str, str, str]] = [
    ("bombolon", "Dolci e pasticceria", "Bomboloni"), ("bombolin", "Dolci e pasticceria", "Bomboloni"),
    ("cornett", "Dolci e pasticceria", "Cornetti"), ("croissant", "Dolci e pasticceria", "Cornetti"),
    ("maritozz", "Dolci e pasticceria", "Maritozzi"), ("zeppol", "Dolci e pasticceria", "Zeppole"),
    ("crostat", "Dolci e pasticceria", "Crostate"), ("tortin", "Dolci e pasticceria", "Torte"), ("muffin", "Dolci e pasticceria", "Muffin"), ("tartell", "Dolci e pasticceria", "Tartellette"), ("zatterin", "Dolci e pasticceria", "Zatterine"),
    ("donut", "Dolci e pasticceria", "Donut"), ("krapfen", "Dolci e pasticceria", "Krapfen"), ("sfogliatin", "Dolci e pasticceria", "Sfogliatine"),
    ("focaccia", "Pane e pizze", "Focaccia"), ("baguette", "Pane e pizze", "Baguette"), ("panino", "Pane e pizze", "Panini"), ("pizzett", "Pane e pizze", "Pizzette"),
    ("limoncello", "Alcolici", "Limoncello"), ("grappa", "Alcolici", "Grappa"), ("spumante", "Alcolici", "Spumante"), ("aperol", "Alcolici", "Aperitivi"),
    ("caciott", "Latticini e formaggi", "Caciotta"), ("pecorino", "Latticini e formaggi", "Pecorino"), ("mascarpone", "Latticini e formaggi", "Mascarpone"),
    ("grana", "Latticini e formaggi", "Grana"), ("mozzarell", "Latticini e formaggi", "Mozzarella"), ("ricott", "Latticini e formaggi", "Ricotta"),
    ("insalata", "Verdura e ortaggi", "Insalata"), ("radicchio", "Verdura e ortaggi", "Radicchio"), ("melanzan", "Verdura e ortaggi", "Melanzane"),
    ("peperon", "Verdura e ortaggi", "Peperoni"), ("zucchin", "Verdura e ortaggi", "Zucchine"), ("prezzemolo", "Verdura e ortaggi", "Erbe aromatiche"),
    ("basilico", "Verdura e ortaggi", "Erbe aromatiche"), ("rosmarino", "Verdura e ortaggi", "Erbe aromatiche"), ("salvia", "Verdura e ortaggi", "Erbe aromatiche"),
    ("erbe aromatiche", "Verdura e ortaggi", "Erbe aromatiche"), ("sedano", "Verdura e ortaggi", "Sedano"), ("carote", "Verdura e ortaggi", "Carote"),
    ("anguria", "Frutta", "Anguria"), ("albicocc", "Frutta", "Albicocche"), ("clementin", "Frutta", "Agrumi"), ("limoni", "Frutta", "Limoni"),
    ("birra", "Alcolici", "Birra"), ("twining", "Caffè e tè", "Tè e tisane"), ("pukka", "Caffè e tè", "Tè e tisane"),
    ("pompadour", "Caffè e tè", "Tè e tisane"), ("tisan", "Caffè e tè", "Tè e tisane"), ("camomilla", "Caffè e tè", "Tè e tisane"),
    ("caffe", "Caffè e tè", "Caffè"), ("succh", "Bevande", "Succhi"), ("succo", "Bevande", "Succhi"),
    ("tullia", "Bevande", "Acqua"), ("lilia", "Bevande", "Acqua"), ("benedetto", "Bevande", "Acqua"), ("acqua", "Bevande", "Acqua"),
    ("xugia", "Dolci e pasticceria", "Cioccolato"), ("fondente", "Dolci e pasticceria", "Cioccolato"), ("olio", "Oli e grassi", "Olio"), ("uova", "Uova", "Uova"), ("uovo", "Uova", "Uova"),
]

NONFOOD_FAMILIES_WITH_TAXONOMY = {"Accessori e ricambi", "Pulizia e igiene", "Materiali e attrezzature", "Monouso e tavola"}

ABBREVIATIONS = {
    "mozz": "mozzarella", "pomo": "pomodori", "croiss": "croissant", "pancet": "pancetta", "yog": "yogurt", "prosc": "prosciutto", "cioc": "cioccolato", "nocc": "nocciola", "zucch": "zucchine",
    "pomod": "pomodori", "cong": "congelato", "sgusc": "sgusciate", "marm": "marmellata", "form": "formaggio",
}

STOPWORDS = {"di", "del", "della", "dei", "delle", "dello", "al", "alla", "alle", "allo", "in", "con", "senza", "e", "a", "da",
             "il", "lo", "la", "le", "i", "gli", "un", "una", "per", "su", "tipo"}

UNIT_WORDS = {"kg", "g", "gr", "l", "lt", "cl", "ml", "pz", "conf", "pezzi", "x", "ct", "cf", "mg"}
ORIGIN_RE = re.compile(r"\bprov\b\.?\s*(.*)$", re.IGNORECASE)


@lru_cache(maxsize=1)
def _categories() -> dict[str, dict]:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf8")).get("categories", {})
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def _nonfood_categories() -> dict[str, dict]:
    try:
        return json.loads(NONFOOD_FILE.read_text(encoding="utf8")).get("categories", {})
    except (OSError, ValueError):
        return {}


def _find_nonfood_taxonomy(tokens: list[str]) -> dict | None:
    """Voce più specifica della tassonomia non alimentare (Open Products/Beauty Facts)."""
    cats = _nonfood_categories()
    best: tuple[int, int, dict] | None = None
    for size in (3, 2, 1):
        for start in range(0, len(tokens) - size + 1):
            window = tokens[start: start + size]
            if size == 1 and len(window[0]) < 5:
                continue
            for last in _variants(window[-1]):
                hit = cats.get(" ".join(window[:-1] + [last]))
                if hit and (best is None or (size, hit["depth"]) > best[:2]):
                    best = (size, hit["depth"], hit)
        if best is not None and size == best[0]:
            break
    return best[2] if best else None


def _variants(token: str) -> list[str]:
    """Singolare/plurale italiano semplice: pomodoro→pomodori, zucchina→zucchine."""
    out = [token]
    if len(token) < 4:
        return out
    stem, last = token[:-1], token[-1]
    if last == "o":
        out += [stem + "i"]
    elif last == "a":
        out += [stem + "e", stem + "i"]
    elif last == "i":
        out += [stem + "o", stem + "e", stem + "a"]
    elif last == "e":
        out += [stem + "i", stem + "a"]
    return out


def _clean_tokens(description: str) -> tuple[list[str], str | None]:
    """Token puliti della descrizione + provenienza (es. «PROV. ITALIA» → Italia)."""
    text = str(description or "")
    origin = None
    m = ORIGIN_RE.search(text)
    if m:
        origin = re.sub(r"\s+", " ", m.group(1)).strip(" .-") or None
        text = text[: m.start()]
    tokens = []
    for tok in normalize_text(text).split():
        if tok.isdigit() or tok in UNIT_WORDS or tok in STOPWORDS:
            continue
        if re.fullmatch(r"\d+(kg|g|gr|l|lt|cl|ml|pz|x\d+)?", tok):
            continue
        tokens.append(ABBREVIATIONS.get(tok, tok))
    return tokens, (origin.title() if origin else None)


def _find_brand(tokens: list[str]) -> str | None:
    joined = " ".join(tokens)
    for key, shown in BRANDS.items():
        if " " in key:
            if key in joined:
                return shown
        elif key in tokens:
            return shown
    for tok in tokens:  # marche attaccate: «MOZZGRIFO», «GRIFOLATTE»
        for key, shown in BRANDS.items():
            if " " not in key and len(key) >= 5 and key in tok and tok != key:
                return shown
    return None


def _find_non_food(tokens: list[str]) -> str | None:
    token_set = set(tokens)
    joined = " ".join(tokens)
    for family, words in NON_FOOD:
        for word in words:
            if (" " in word and word in joined) or word in token_set:
                return family
    return None


def _find_extra(tokens: list[str]) -> dict | None:
    for tok in tokens:
        for stem, macro, label in EXTRA_FOODS:
            if (len(stem) >= 6 and stem in tok) or tok.startswith(stem):
                return {"macro": macro, "label": label, "depth": 1}
    return None


def _find_category(tokens: list[str]) -> dict | None:
    extra = _find_extra(tokens)
    if extra:
        return extra
    cats = _categories()
    if not cats:
        return None
    best: tuple[int, int, dict] | None = None
    for size in (3, 2, 1):
        for start in range(0, len(tokens) - size + 1):
            window = tokens[start: start + size]
            # varianti solo sull'ultima parola (pomodoro → pomodori)
            for last in _variants(window[-1]):
                key = " ".join(window[:-1] + [last])
                hit = cats.get(key)
                if hit and len(window[-1]) >= 4 or (hit and size > 1):
                    cand = (size, hit["depth"], hit)
                    if best is None or cand[:2] > best[:2]:
                        best = cand
        if best is not None and size == best[0]:
            break
    return best[2] if best else None


def recognize(description: str) -> dict:
    """Riconosce famiglia, categoria, marca e provenienza. Mai solleva eccezioni."""
    try:
        tokens, origin = _clean_tokens(description)
        brand = _find_brand(tokens)
        non_food = _find_non_food(tokens)
        category = _find_category(tokens)
        if category and non_food is None:
            return {"kind": "food", "category": category["macro"], "subcategory": category["label"], "brand": brand, "origin": origin, "confidence": 0.8}
        if non_food:
            tax = _find_nonfood_taxonomy(tokens) if non_food in NONFOOD_FAMILIES_WITH_TAXONOMY else None
            return {"kind": "non_food", "category": non_food, "subcategory": tax["label"] if tax else None, "brand": brand, "origin": origin, "confidence": 0.7}
        tax = _find_nonfood_taxonomy(tokens)
        if tax:
            return {"kind": "non_food", "category": tax["family"], "subcategory": tax["label"], "brand": brand, "origin": origin, "confidence": 0.5}
        if brand:
            return {"kind": "food", "category": None, "subcategory": None, "brand": brand, "origin": origin, "confidence": 0.5}
        return {"kind": "unknown", "category": None, "subcategory": None, "brand": None, "origin": origin, "confidence": 0.0}
    except Exception:  # noqa: BLE001 - il riconoscimento non deve mai rompere ricerche e report
        return {"kind": "unknown", "category": None, "subcategory": None, "brand": None, "origin": None, "confidence": 0.0}


def annotate(items: list[dict]) -> list[dict]:
    """Aggiunge ``recognition`` a ogni prodotto del catalogo (non altera gli altri campi)."""
    for item in items:
        if isinstance(item, dict):
            item["recognition"] = recognize(item.get("nome_canonico") or item.get("name") or item.get("descrizione") or "")
    return items


def compatible(wanted: dict, got: dict) -> bool:
    """Una riga (riconosciuta come ``got``) può stare nel confronto del prodotto cercato (``wanted``)?"""
    if got["kind"] == "non_food" and got["category"] == "Imposte e voci contabili" and wanted.get("category") != got["category"]:
        return False
    if wanted["kind"] == "non_food" and got["kind"] == "non_food" and wanted["category"] != got["category"]:
        return False
    # Cerco un alimento: scarto accessori/attrezzature (dispenser, dosatori) e dolci pronti (crostata alla marmellata).
    if wanted["kind"] == "food" and got["kind"] == "non_food":
        return False
    if wanted["kind"] == "food" and got["kind"] == "food" and got["category"] == "Dolci e pasticceria" and wanted["category"] != "Dolci e pasticceria":
        return False
    return True


# Ricerche dove le varianti (formato, misura) vanno scelte a mano: non si fondono in un solo prodotto.
KEEP_VARIANTS = {"acqua", "carta igienica", "c igienica", "c ig", "carta a4", "a4", "lamp", "lampada", "lampade", "lampadina", "lampadine"}


def collapse_to_product(items: list[dict], query: str) -> list[dict]:
    """Un solo prodotto con tutti i produttori/varianti trovati («crostata» ≠ 5 righe separate).

    Fonde gli elementi del catalogo che la ricerca ha trovato e che sono compatibili con il prodotto cercato;
    ``canonical_names`` conserva tutti i nomi originali per storico e confronto fornitori.
    """
    try:
        from .product_taxonomy import extract_product_query

        q = normalize_text(extract_product_query(query) or query).strip()
        if not q or len(q.split()) > 2 or q in KEEP_VARIANTS:
            return items
        wanted = recognize(q)
        if wanted["kind"] == "unknown":
            return items
        same, other = [], []
        for item in items:
            name = str(item.get("nome_canonico") or "")
            (same if name and compatible(wanted, recognize(name)) else other).append(item)
        if len(same) < 2:
            return items
        names: list[str] = []
        for item in same:
            for n in item.get("canonical_names") or [item.get("nome_canonico")]:
                if n and n not in names:
                    names.append(n)
        top = max(same, key=lambda i: int(i.get("purchases") or 0))
        purchases = sum(int(i.get("purchases") or 0) for i in same)
        merged = {**top, "nome_canonico": q.title(), "canonical_names": names, "purchases": purchases, "marca": None}
        mins = [float(i["min_price"]) for i in same if i.get("min_price") is not None]
        maxs = [float(i["max_price"]) for i in same if i.get("max_price") is not None]
        if mins:
            merged["min_price"] = min(mins)
        if maxs:
            merged["max_price"] = max(maxs)
        weighted = [(float(i["avg_price"]), int(i.get("purchases") or 0)) for i in same if i.get("avg_price") is not None]
        if weighted:
            weight = sum(w for _, w in weighted)
            merged["avg_price"] = round(sum(p * w for p, w in weighted) / weight, 4) if weight else round(sum(p for p, _ in weighted) / len(weighted), 4)
        merged["merged_variants"] = len(same)
        return sorted([merged, *other], key=lambda i: str(i.get("nome_canonico") or ""))
    except Exception:  # noqa: BLE001
        return items
