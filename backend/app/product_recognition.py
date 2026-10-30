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
    # Tovaglioli di carta (plurale o con «2V», «PZ», «CT») ≠ tovagliolo di stoffa a noleggio.
    if token_set & {"tovagliolo", "tovaglioli"} and not token_set & {"lavanolo", "lavaggio", "servizio", "noleggio"}:
        if "tovaglioli" in token_set or token_set & {"2v", "carta", "veline"} or any(t.endswith("pz") or t.startswith("ct") for t in token_set):
            return "Monouso e tavola"
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
    # Solo accessori veri: parole come «sgrassato», «vassoio», «busta» descrivono il confezionamento di un alimento.
    if wanted["kind"] == "food" and got["kind"] == "non_food" and got["category"] == "Accessori e ricambi":
        return False
    if wanted["kind"] == "food" and got["kind"] == "food" and got["category"] == "Dolci e pasticceria" and wanted["category"] != "Dolci e pasticceria":
        return False
    return True


# Ricerche dove le varianti (formato, misura) vanno scelte a mano: non si fondono in un solo prodotto.
KEEP_VARIANTS = {"acqua", "carta igienica", "c igienica", "c ig", "carta a4", "a4", "lamp", "lampada", "lampade", "lampadina", "lampadine"}


def _merge_group(same: list[dict], label: str) -> dict:
    """Fonde più voci di catalogo in una sola (nomi originali conservati in ``canonical_names``)."""
    names: list[str] = []
    for item in same:
        for n in item.get("canonical_names") or [item.get("nome_canonico")]:
            if n and n not in names:
                names.append(n)
    top = max(same, key=lambda i: int(i.get("purchases") or 0))
    merged = {**top, "nome_canonico": label, "canonical_names": names, "purchases": sum(int(i.get("purchases") or 0) for i in same), "marca": None}
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
    return merged


def _majority_family(items: list[dict]) -> tuple[dict, list[dict]] | None:
    """Ricerca incompleta («crost») o lunga: la famiglia si deduce dalle voci trovate, non dal testo digitato.

    Se almeno due voci (e la metà del totale) sono riconosciute nella stessa famiglia/sottocategoria, quelle
    si fondono; le altre restano separate.
    """
    from collections import Counter

    recs = [(item, recognize(str(item.get("nome_canonico") or ""))) for item in items]
    keys = Counter((r["kind"], r["category"], r["subcategory"]) for _, r in recs if r["kind"] != "unknown" and r["subcategory"])
    if not keys:
        return None
    (kind, category, sub), count = keys.most_common(1)[0]
    if count < 2 or count * 2 < len(items):
        return None
    if kind == "non_food" and category == "Imposte e voci contabili":
        return None
    group = [item for item, r in recs if (r["kind"], r["category"], r["subcategory"]) == (kind, category, sub)]
    return {"kind": kind, "category": category, "subcategory": sub}, group


def _collapse_core(items: list[dict], query: str) -> list[dict]:
    """Un solo prodotto con tutti i produttori/varianti trovati («crostata» ≠ 5 righe separate).

    Fonde gli elementi del catalogo che la ricerca ha trovato e che sono compatibili con il prodotto cercato;
    ``canonical_names`` conserva tutti i nomi originali per storico e confronto fornitori. Le voci incompatibili
    (dolci pronti, accessori) vengono escluse. Se la ricerca è incompleta o lunga (es. «crost», 3+ parole) la
    famiglia si ricava dalle voci stesse.
    """
    try:
        from .product_taxonomy import extract_product_query

        q = normalize_text(extract_product_query(query) or query).strip()
        if not q or q in KEEP_VARIANTS or len(items) < 2:
            return items
        wanted = recognize(q) if len(q.split()) <= 2 else {"kind": "unknown"}
        if wanted["kind"] == "unknown":
            found = _majority_family(items)
            if not found:
                return items
            family, group = found
            label = str(family["subcategory"]).title()
            rest = [i for i in items if i not in group]
            return [_merge_group(group, label), *rest]
        same, other = [], []
        for item in items:
            name = str(item.get("nome_canonico") or "")
            (same if name and compatible(wanted, recognize(name)) else other).append(item)
        if len(same) < 2:
            return items
        words = {w for i in same for w in normalize_text(str(i.get("nome_canonico") or "")).split()}
        if all(t in words for t in q.split()):
            label = q.title()
        else:
            # Parola tagliata («crostat»): completa con la parola più frequente che inizia così.
            from collections import Counter

            starts = Counter(w for i in same for w in normalize_text(str(i.get("nome_canonico") or "")).split() if w.startswith(q.split()[0]))
            label = (starts.most_common(1)[0][0] if starts else (wanted.get("subcategory") or q)).title()
        # Le voci non compatibili (cornetti alla marmellata, dispenser…) non sono il prodotto cercato: fuori, come in Ask.
        return [_merge_group(same, label)]
    except Exception:  # noqa: BLE001
        return items


_FILLER_WORDS = {"a", "al", "all", "alla", "alle", "allo", "agli", "ai", "con", "da", "dei", "del", "della", "delle", "di", "e", "il", "in", "la", "le", "lo", "per", "su", "un", "una"}
_SYNONYM_STEMS = {
    "marm": "marmellat", "marmellata": "marmellat", "marmellate": "marmellat",
    "confettura": "marmellat", "confetture": "marmellat", "confet": "marmellat",
    "choco": "cioccolat", "chocolate": "cioccolat", "cioccolato": "cioccolat", "cioccolata": "cioccolat",
    "ciocc": "cioccolat", "cioc": "cioccolat", "cioco": "cioccolat",
    "bombolone": "bombolon", "bomboloni": "bombolon", "bombolino": "bombolon", "bombolini": "bombolon",
}


def name_signature(name: str) -> frozenset[str]:
    """Impronta di un nome prodotto: parole utili, senza articoli/preposizioni e senza desinenza (plurale/femminile).

    «crostata marmellata», «crostate alla marmellata», «crostate alle marmellate» → stessa impronta.
    Numeri e formati restano nell'impronta: «acqua 75x12» e «acqua 100x12» non si confondono.
    """
    out = set()
    for tok in normalize_text(name).split():
        if tok in _FILLER_WORDS:
            continue
        tok = _SYNONYM_STEMS.get(tok, tok)
        if len(tok) >= 5 and tok[-1] in "aeio" and not any(ch.isdigit() for ch in tok):
            tok = tok[:-1]
        if tok in _SYNONYM_STEMS.values() or tok:
            out.add(_SYNONYM_STEMS.get(tok, tok))
    return frozenset(out)


def merge_equivalent_names(items: list[dict]) -> list[dict]:
    """Fonde le voci che sono lo stesso prodotto scritto in modi diversi (singolare/plurale, articoli, sinonimi).

    Vale anche senza testo di ricerca (elenco catalogo): una sola riga per prodotto con tutti i produttori;
    i nomi originali restano in ``canonical_names``. Si fondono solo voci con impronta identica e stessa
    famiglia riconosciuta.
    """
    try:
        groups: dict[tuple, list[dict]] = {}
        order: list[tuple] = []
        for item in items:
            name = str(item.get("nome_canonico") or "")
            sig = name_signature(name)
            rec = recognize(name)
            key = (sig, rec["kind"], rec["category"], rec["subcategory"]) if sig else ("__solo__", id(item))
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(item)
        out: list[dict] = []
        for key in order:
            group = groups[key]
            if len(group) < 2:
                out.extend(group)
                continue
            top = max(group, key=lambda i: int(i.get("purchases") or 0))
            label = str(top.get("nome_canonico") or "")
            out.append(_merge_group(group, label[:1].upper() + label[1:]))
        return out
    except Exception:  # noqa: BLE001
        return items


def collapse_to_product(items: list[dict], query: str) -> list[dict]:
    """Un prodotto per ricerca (vedi ``_collapse_core``) e, in ogni caso, nomi equivalenti fusi in una sola voce."""
    from .product_taxonomy import extract_product_query  # noqa: F401  (stesso import del core)

    q = normalize_text(extract_product_query(query) or query).strip() if query else ""
    result = _collapse_core(items, query)
    if q in KEEP_VARIANTS:
        return apply_user_groups(result)
    return apply_user_groups(merge_equivalent_names(result))


# --- Gruppi confermati dall'utente -------------------------------------------------
# «Questi nomi sono lo stesso prodotto»: la scelta viene salvata (tabella settings) e vale
# per ogni ricerca, catalogo e report storico. Le regole automatiche restano valide.
_USER_GROUPS: list[list[str]] = []


def set_user_groups(groups: list[list[str]]) -> None:
    global _USER_GROUPS
    _USER_GROUPS = [[normalize_text(n) for n in g if n] for g in groups if g and len([n for n in g if n]) >= 2]


def get_user_groups() -> list[list[str]]:
    return [list(g) for g in _USER_GROUPS]


def apply_user_groups(items: list[dict]) -> list[dict]:
    """Fonde le voci i cui nomi (anche quelli già fusi in ``canonical_names``) stanno nello stesso gruppo."""
    if not _USER_GROUPS or len(items) < 2:
        return items
    try:
        def names_of(item: dict) -> list[str]:
            return [normalize_text(n) for n in (item.get("canonical_names") or [item.get("nome_canonico")]) if n]

        buckets: dict[int, list[dict]] = {}
        order: list[tuple[str, int]] = []
        for item in items:
            gi = next((i for i, g in enumerate(_USER_GROUPS) if any(n in g for n in names_of(item))), None)
            if gi is None:
                order.append(("solo", id(item)))
                buckets[id(item)] = [item]
            else:
                if ("grp", gi) not in order:
                    order.append(("grp", gi))
                buckets.setdefault(-1 - gi, []).append(item)
        out: list[dict] = []
        for kind, ref in order:
            group = buckets[ref] if kind == "solo" else buckets[-1 - ref]
            if len(group) < 2:
                out.extend(group)
                continue
            top = max(group, key=lambda i: int(i.get("purchases") or 0))
            label = str(top.get("nome_canonico") or "")
            merged = _merge_group(group, label)
            merged["user_group"] = True
            out.append(merged)
        return out
    except Exception:  # noqa: BLE001
        return items
