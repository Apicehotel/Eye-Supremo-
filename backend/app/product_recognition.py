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
    ("crostat", "Dolci e pasticceria", "Crostate"), ("tortin", "Dolci e pasticceria", "Torte"), ("muffin", "Dolci e pasticceria", "Muffin"),
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
            return {"kind": "non_food", "category": non_food, "subcategory": None, "brand": brand, "origin": origin, "confidence": 0.7}
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
