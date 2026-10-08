"""Small, local taxonomy layer inspired by Shopify's product taxonomy.

It deliberately contains only high-confidence Italian aliases used by the
hotel catalog. Raw invoice descriptions are never overwritten.
"""

from collections import defaultdict
import re
from decimal import Decimal
from rapidfuzz import fuzz
from .normalization import extract_content, normalize_text

PRODUCT_FAMILY_ALIASES = {
    # Never use the bare substring ``lamp`` as the only remote query: it
    # matches unrelated words such as lampone and lampante.
    "lamp": ("lampada", "lampade", "lampadina", "lampadine", "portalampada", "portalampade"),
    "lampada": ("lampada", "lampade", "lampadina", "lampadine", "portalampada", "portalampade"),
    "lampadine": ("lampadina", "lampadine"),
    "carta a4": ("carta a4", "carta fotoc a4", "risma a4"),
    "a4": ("carta a4", "carta fotoc a4", "risma a4"),
    "acqua": ("acqua", "acque", "tullia", "lilia", "levissima", "san benedetto", "sant'anna"),
    # Common invoice shorthand: suppliers often omit the final letters of
    # "carta" while keeping the discriminating word "igienica".
    "c igienica": ("carta igienica", "c igienica"),
    "carta igienica": ("carta igienica", "c igienica"),
    "c ig": ("carta igienica", "c ig"),
    # Include mini/composti: in fattura spesso "MINIBOMBOLONI" o "mini bomboloni".
    "bomboloni": (
        "bomboloni", "bombolino", "bombolini", "bombolone",
        "mini bomboloni", "mini bombolone", "mini bombolini", "mini bombolino",
        "minibomboloni", "minibombolone", "minibombolini", "minibombolino",
    ),
    "bombolone": (
        "bomboloni", "bombolino", "bombolini", "bombolone",
        "mini bomboloni", "mini bombolone", "mini bombolini", "mini bombolino",
        "minibomboloni", "minibombolone", "minibombolini", "minibombolino",
    ),
}

# Stem sicuri per match substring (es. minibomboloni). Mai "bombol": matcherebbe bombola.
PRODUCT_FAMILY_STEMS = {
    "bomboloni": "bombolon",
    "bombolone": "bombolon",
}

# Famiglie con collisioni note: la riga deve contenere almeno uno di questi token.
PRODUCT_REQUIRED_SUBSTRINGS = {
    "bomboloni": ("bombolin", "bombolon"),
    "bombolone": ("bombolin", "bombolon"),
}

# Stem generici troppo corti/ambigui: non usarli in ILIKE substring.
UNSAFE_GENERIC_STEMS = {"bombol", "lamp", "acqu", "cart"}

# These are invoice line items, not products. Keep them available to the
# supplier/expense views, but out of the product catalogue and its search.
NON_PRODUCT_TOKENS = {
    "carburante", "benzina", "gasolio", "diesel", "consegna", "trasporto",
    "spedizione", "corriere", "manodopera", "servizio", "servizi", "consulenza",
    "installazione", "assistenza", "noleggio", "canone", "commissione", "pedaggio",
    "diritto", "diritti", "costo", "costi", "spese", "smaltimento",
}
NON_PRODUCT_PREFIXES = (
    "carbur", "benzin", "gasol", "consegn", "trasport", "spedit", "corrier",
    "manodoper", "serviz", "consulen", "install", "assistenz", "nolegg", "canon",
    "commission", "pedagg", "diritt", "cost", "spes", "smaltiment",
)


def is_catalog_product(description: str) -> bool:
    """Return whether an invoice description belongs in the product catalogue."""
    text = normalize_text(description).strip()
    if not text:
        return False
    tokens = set(text.split())
    if tokens & NON_PRODUCT_TOKENS:
        return False
    return not text.startswith(("servizio ", "prestazione ", "quota ", "spese "))


def is_non_product_query(query: str) -> bool:
    """Identify searches aimed at invoice services rather than goods."""
    tokens = normalize_text(query).split()
    return any(token in NON_PRODUCT_TOKENS or token.startswith(NON_PRODUCT_PREFIXES) for token in tokens)


# Parole tipiche delle domande Ask: non devono entrare in FTS/ILIKE come AND.
QUESTION_FILLERS = {
    "quanto", "quale", "quali", "chi", "cosa", "come", "dove", "quando", "perche", "perché",
    "ho", "hai", "abbiamo", "hanno", "mi", "ti", "ci", "si", "lo", "la", "le", "li", "gli",
    "il", "i", "un", "una", "uno", "del", "della", "dei", "delle", "degli", "dal", "dalla",
    "da", "di", "in", "nel", "nella", "nei", "negli", "nelle", "su", "sul", "sulla", "per",
    "con", "tra", "fra", "e", "o", "a", "al", "alla", "ai", "alle",
    "speso", "pagato", "costo", "costa", "costano", "prezzo", "prezzi", "media", "medio",
    "vende", "vendono", "fornitore", "fornitori", "fornisce", "meglio", "peggio", "migliore",
    "migliori", "peggiore", "peggiori", "confronta", "confronto", "storico", "totale",
    "fattura", "fatture", "prodotto", "prodotti", "acquisto", "acquisti", "acquistato",
    "fammi", "vedere", "mostra", "dimmi", "trova", "cerca", "elenco", "lista", "classifica",
    "analizza", "analisi", "risulta", "archivio", "locale", "tutti", "tutte", "piu", "più",
    "meno", "alto", "alta", "basso", "bassa", "ultimo", "ultima", "recente",
}


def extract_product_query(query: str) -> str:
    """Estrae il prodotto da una domanda in linguaggio naturale.

    Senza questo, Ask manda in ricerca tutta la frase
    («chi mi vende meglio i bomboloni») e FTS/ILIKE richiedono
    anche «chi»/«vende»/«meglio» sulla riga fattura → zero risultati.
    """
    normalized = normalize_text(query).strip()
    if not normalized:
        return ""
    # Alias multi-parola noti (es. «carta igienica») hanno priorità.
    for alias in sorted(PRODUCT_FAMILY_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return alias
    tokens = [t for t in normalized.split() if t not in QUESTION_FILLERS and len(t) >= 3]
    # Singolo token che coincide con un alias o una sua variante.
    for token in tokens:
        if token in PRODUCT_FAMILY_ALIASES:
            return token
        for key, variants in PRODUCT_FAMILY_ALIASES.items():
            if token in variants:
                return key
            if any(token.startswith(v[: max(4, len(v) - 1)]) for v in variants if len(v) >= 4):
                return key
    return " ".join(tokens) if tokens else normalized


def search_terms(query: str) -> tuple[str, ...]:
    """Varianti di ricerca per QUALSIASI prodotto in fattura, non solo alias noti."""
    needle = extract_product_query(query)
    normalized = normalize_text(needle).strip()
    if not normalized:
        return (query.strip(),) if query.strip() else ()
    if normalized in PRODUCT_FAMILY_ALIASES:
        return PRODUCT_FAMILY_ALIASES[normalized]
    # Prodotti fuori tassonomia: tieni il needle + forma senza ultima vocale
    # (limoncelli←limoncello, pavimenti←pavimento) senza aprire substring pericolose.
    variants = [normalized]
    for token in normalized.split():
        if len(token) >= 6 and token[-1] in "aeiou":
            stem = token[:-1]
            if stem not in UNSAFE_GENERIC_STEMS and stem not in variants:
                variants.append(stem)
        if token not in variants:
            variants.append(token)
    return tuple(dict.fromkeys(variants))


def product_stem(query: str) -> str | None:
    """Stem per match substring su ogni prodotto (minibomboloni, minilimoncello, …)."""
    needle = normalize_text(extract_product_query(query) or query).strip()
    if not needle:
        return None
    if needle in PRODUCT_FAMILY_STEMS:
        return PRODUCT_FAMILY_STEMS[needle]
    for key, stem in PRODUCT_FAMILY_STEMS.items():
        if needle in PRODUCT_FAMILY_ALIASES.get(key, ()):
            return stem
    # Stem generico: token più lungo, togli desinenza plurale/vocale finale.
    token = max(needle.split(), key=len)
    if len(token) < 7:
        return None
    stem = token
    for suffix in ("zioni", "ioni", "oni", "ini", "ina", "one", "ani", "i", "e", "a", "o"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 6:
            stem = token[: -len(suffix)]
            break
    if len(stem) < 6 or stem in UNSAFE_GENERIC_STEMS:
        return None
    return stem


def required_substrings(query: str) -> tuple[str, ...] | None:
    """Token obbligatori anti-collisione (bomboloni≠bombola). None = nessun vincolo extra."""
    needle = normalize_text(extract_product_query(query) or query).strip()
    if needle in PRODUCT_REQUIRED_SUBSTRINGS:
        return PRODUCT_REQUIRED_SUBSTRINGS[needle]
    for key, required in PRODUCT_REQUIRED_SUBSTRINGS.items():
        if needle in PRODUCT_FAMILY_ALIASES.get(key, ()):
            return required
    return None


def description_matches_product(description: str, query: str) -> bool:
    """True se la descrizione riga fattura appartiene al prodotto cercato (qualsiasi)."""
    text = normalize_text(description)
    if not text:
        return False
    compact = text.replace(" ", "")
    words = text.split()
    required = required_substrings(query)
    if required and not any(token in text or token in compact for token in required):
        return False
    stem = product_stem(query)
    if stem and (stem in compact or stem in text):
        return True
    needle = normalize_text(extract_product_query(query) or query)
    if not needle:
        return False
    for term in search_terms(needle):
        term_n = normalize_text(term)
        if not term_n:
            continue
        if term_n in text or term_n.replace(" ", "") in compact:
            return True
        # Token della query tutti presenti (ordine libero) nella descrizione.
        term_tokens = [t for t in term_n.split() if len(t) >= 3]
        if term_tokens and all(any(t in w or w.startswith(t[: max(4, len(t) - 1)]) for w in words) for t in term_tokens):
            return True
        # Parola composta: limoncello ⊂ minilimoncello / limoncello70cl
        if len(term_n) >= 5 and any(term_n in w or (len(term_n) >= 6 and term_n[:-1] in w) for w in words):
            return True
    return False


def row_matches_product_query(description: str, query: str) -> bool:
    """Filtro post-ricerca: anti-collisione se serve, altrimenti accetta match motore."""
    if not (query or "").strip():
        return bool(str(description or "").strip())
    required = required_substrings(query)
    if not required:
        # Nessuna collisione nota: tieni i hit di FTS/cache/centrale.
        return bool(str(description or "").strip())
    text = normalize_text(description)
    compact = text.replace(" ", "")
    return any(token in text or token in compact for token in required)


def diversify_by_supplier(
    records: list[dict],
    *,
    supplier_key: str = "supplier",
    limit: int | None = None,
) -> list[dict]:
    """Interleave per fornitore: la prima pagina non è monopolizzata da un solo vendor."""
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in records:
        key = str(row.get(supplier_key) or "—")
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(row)
    out: list[dict] = []
    while any(buckets.values()):
        for key in order:
            if buckets.get(key):
                out.append(buckets[key].pop(0))
                if limit is not None and len(out) >= limit:
                    return out
    return out


def supplier_breakdown(records: list[dict], *, supplier_key: str = "supplier") -> list[dict]:
    """Conteggio fornitori sul match set completo (per UI/Ask)."""
    counts: dict[str, int] = {}
    for row in records:
        key = str(row.get(supplier_key) or "—")
        counts[key] = counts.get(key, 0) + 1
    return [
        {"supplier": name, "rows": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    ]


def is_family_match(description: str, query: str) -> bool:
    """Apply token-level guards after the central substring search.

    Supabase's catalogue RPC intentionally supports loose text search. The
    report layer must add semantic boundaries so ``lampadine`` cannot return
    ``lampone`` and ``carta a4`` cannot return every object whose description
    merely contains the size code A4.
    """
    text = normalize_text(description)
    tokens = set(text.split())
    normalized = normalize_text(query).strip()
    if normalized == "lampadine":
        if tokens & {"bicchiere", "stampa", "sagomati", "kit", "saldatura"}:
            return False
        return bool(tokens & {"lampadina", "lampadine"})
    if normalized in {"lamp", "lampada"}:
        if tokens & {"kit", "saldatura", "decorazione", "cappelli", "piastre", "insect", "killer", "stampa", "sagomati", "bicchiere", "bottiglie"}:
            return False
        return bool(tokens & {"lamp", "lampada", "lampade", "lampadina", "lampadine", "portalampada", "portalampade"})
    if normalized in {"a4", "carta a4"}:
        return ("carta" in tokens and "a4" in tokens) or "risma" in tokens and "a4" in tokens
    if normalized == "acqua":
        # Prefer drinking-water signals. A plain substring match would also
        # return utilities, maintenance, detergents and food prepared ``in
        # acqua``.
        if tokens & {"acquedotto", "acquaragia", "ossigenata", "pompa", "tubo", "disgorgo", "stagnante", "tariffa", "quota", "oneri", "ricalcolo", "restituzione", "sconto", "trattamento", "analisi", "controllo", "intervento", "manodopera", "ore", "riduttore", "ventilconvettore", "salgemma", "spingiacqua", "distributore"}:
            return False
        if text == "acqua" or text == "acque":
            return True
        beverage = {"minerale", "naturale", "frizzante", "gassata", "bottiglia", "benedetto", "leviss", "lilia", "tullia", "tonica", "wellness", "brick", "pet", "sant"}
        if tokens & {"tullia", "lilia", "leviss", "benedetto", "levissima", "sanbenedetto"}:
            return True
        return ("acqua" in tokens or "acque" in tokens) and bool(tokens & beverage)
    return True


def is_product_search_match(description: str, query: str) -> bool:
    """Reject broad central-search hits unrelated to the displayed name."""
    text = normalize_text(description)
    query_text = normalize_text(query).strip()
    if not query_text:
        return True
    if is_non_product_query(query_text):
        return False
    if query_text in PRODUCT_FAMILY_ALIASES:
        if query_text in {"c igienica", "carta igienica", "c ig"}:
            return "igienica" in tokens and ("carta" in tokens or "c" in tokens)
        return is_family_match(description, query_text)
    terms = search_terms(query_text)
    tokens = set(text.split())

    def matches(token: str) -> bool:
        if token in tokens:
            return True
        # Accept small typographical errors such as ``igenica``/``igienica``
        # without turning short or unrelated searches into broad matches.
        return any(
            len(token) >= 5 and abs(len(candidate) - len(token)) <= 2
            and fuzz.ratio(token, candidate) >= 82
            for candidate in tokens
        )

    return any(all(matches(token) for token in normalize_text(term).split()) for term in terms)


def product_content_group(item: dict) -> tuple[str, str] | None:
    """Return a stable group for the same product and normalized content."""
    name = str(item.get("nome_canonico") or "")
    normalized = normalize_text(name)
    content = extract_content(name)
    # Water suppliers often encode the format as ``75x12`` or ``100 x 12``
    # without an explicit litre unit. Keep that package format in the key so
    # equal water types with different case sizes never get merged.
    split_litre_package = re.search(r"\b(?:lt|l)\s+(\d+)\s+(\d+)\s*x\s*(\d+)\b", normalized)
    package_match = re.search(r"\b(\d+(?:\s+\d+)?(?:[.,]\d+)?)\s*(?:cl|ml|lt|l)?\s*x\s*(\d+)\b", normalized)
    package_format = None
    if split_litre_package:
        package_format = f"{split_litre_package.group(1)},{split_litre_package.group(2)}x{split_litre_package.group(3)}"
    elif package_match:
        package_format = re.sub(r"\s+", "", package_match.group(0))
    water_tokens = {"acqua", "acque", "tullia", "lilia", "levissima", "leviss", "benedetto", "sanbenedetto", "santanna"}
    water_hint = bool(set(normalized.split()) & water_tokens)
    # OCR sometimes splits a decimal and mislabels litres as centilitres:
    # ``0 75 cl`` is the same catalogue content as ``0,75 l``.
    decimal_cl = re.search(r"\b0\s+(\d{1,2})\s*cl\b", normalized)
    if decimal_cl:
        litres = Decimal(f"0.{decimal_cl.group(1)}")
        content = (litres, "l", litres)
    decimal_cc = re.search(r"\b(\d+(?:[.,]\d+)?)\s*cc\b", normalized)
    if decimal_cc:
        litres = Decimal(decimal_cc.group(1).replace(",", ".")) / Decimal("1000")
        content = (litres, "l", litres)
    # Package counts (``6 pz``, ``24 pezzi``) are not product content.
    if content[1] not in {"kg", "l"} or not content[2] or content[2] <= 0:
        # The central catalogue contains compact half-litre water variants.
        if package_format and water_hint:
            # The package count is the comparable format; the dummy content
            # only lets the family/type normalization continue below.
            content = (Decimal("1"), "l", Decimal("1"))
        elif "acqua" in normalized and "0 5" in normalized:
            content = (Decimal("0.5"), "l", Decimal("0.5"))
        elif "acqua" in normalized and ("0 500" in normalized or "05" in normalized.split()):
            content = (Decimal("0.5"), "l", Decimal("0.5"))
        else:
            # Some catalogues encode the same toilet-paper pack as
            # ``cf8x12rt`` or ``ct8x12r``. Normalize only these explicit
            # package abbreviations; bare piece counts remain ungrouped.
            package_family = re.sub(r"(?<![a-z])(?:cf|ct)(?=\d)", "cf", normalized)
            package_family = re.sub(r"(?<=\d)r\b", "rt", package_family)
            if re.search(r"\bcf\d+x\d+rt\b", package_family):
                return (package_family, "package")
            return None
    family = normalized
    # Remove only packaging/content markers. The remaining product identity
    # keeps brand, flavour and model differences separate.
    family = re.sub(r"\b\d+(?:[.,]\d+|\s+\d+)?\s*(?:kg|kili|chili|chilo|kilo|grammi|grammo|gr|g|hg|etti|etto|litri|litro|ltr|lt|l|ml|cl|cc|dl|pezzi|pezzo|pcs|pc|pz|n|nr|num)\b", " ", family)
    family = re.sub(r"\b(?:kg|kili|chili|chilo|kilo|grammi|grammo|gr|g|hg|etti|etto|litri|litro|ltr|lt|l|ml|cl|cc|dl)\s*\d+(?:[.,]\d+|\s+\d+)?\b", " ", family)
    family = re.sub(r"\b(?:conf|confez|confezione|confezioni)\s+(?:da\s+)?\d+\b", " ", family)
    # Suppliers alternate between ``20 cl x 24`` and ``24 x 200 ml``.
    # Remove the complete package marker from the identity; the normalized
    # content remains the grouping key.
    family = re.sub(r"\b\d+\s*x\s*\d+(?:[.,]\d+)?\s*(?:kg|g|gr|l|lt|ml|cl)\b", " ", family)
    family = re.sub(r"\b\d+\s*(?:pz|pezzi|pcs|pc|n|nr|num)\b|\bx\s*\d+\b", " ", family)
    family = re.sub(r"\b(?:pz|pcs|pc|n|nr|num)\s*\d+\b|\bx\b", " ", family)
    family = re.sub(r"\b(?:conf|confez|confezione|confezioni|da|in)\b", " ", family)
    family = " ".join(family.split())
    # These prefixes are supplier/catalogue abbreviations, not the product
    # identity. Removing them lets equivalent Pago descriptions converge
    # without making different flavours converge on the shared brand name.
    family = re.sub(r"^(?:bev|beve|bevanda|bevande|nett)\s+", "", family)
    if not family:
        return None
    # Water is commonly entered with natural/frizzante/package wording; keep
    # the established family merge for it, while other products use identity.
    if (set(family.split()) & water_tokens) and not any(token in family.split() for token in ("acquaragia", "acquaossigenata")):
        water_type = "naturale" if any(token in family.split() for token in ("naturale", "nat")) else "frizzante" if any(token in family.split() for token in ("frizzante", "gassata", "gas", "friz")) else "tonica" if "tonica" in family.split() else "acqua"
        family = f"acqua {water_type}"
        if package_format:
            return (family, package_format)
    # For solvents the brand/line is not a distinct product in the catalogue:
    # ``acquaragia 603``, ``acquaragia silver`` and ``acquaragia inodore``
    # must share the same content group when the user compares prices.
    if "acquaragia" in family.split():
        family = "acquaragia"
    return (family, str(content[2].normalize()))


def product_family_similarity(left: str, right: str) -> int:
    """Score two normalized product families without ignoring their tokens."""
    return int(fuzz.token_set_ratio(left, right))


def normalize_product_display_name(name: str) -> str:
    """Make catalogue labels readable without changing the source alias."""
    value = normalize_text(name)
    # OCR commonly splits decimal separators and glues the unit to the value.
    def decimal_label(match: re.Match[str]) -> str:
        return f"{Decimal(f'0.{match.group(1)}').normalize():f}".rstrip("0").rstrip(".").replace(".", ",")

    value = re.sub(r"\b0\s+(\d{1,3})\b", decimal_label, value)
    value = re.sub(r"\bcl\s*(\d+)(?=x|\b)", r"\1 cl", value)
    value = re.sub(r"\b(\d+)\s*clx\s*(\d+)\b", r"\1 cl x \2", value)
    value = re.sub(r"(?<![a-z])ct(?=\d)", "cf", value)
    value = re.sub(r"(?<=\d)r\b", "rt", value)
    value = re.sub(r"\b(\d+)\s*ml\b", r"\1 ml", value)
    value = re.sub(r"\b(\d+)\s*x\s*(\d+)\b", r"\1 x \2", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:1].upper() + value[1:] if value else value


def merge_product_catalog(items: list[dict], collapse_family: str | None = None) -> list[dict]:
    """Merge same-product variants by content while preserving source names.

    ``collapse_family`` is used only for explicit family searches such as
    ``acqua``: the picker shows one family row, while canonical source names
    remain attached for the detail/history lookup.
    """
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    passthrough: list[dict] = []
    for item in items:
        key = product_content_group(item)
        if collapse_family == "acqua":
            item_tokens = set(normalize_text(str(item.get("nome_canonico") or "")).split())
            # Family search also has rows without a parseable volume, such as
            # "6 pz acqua ...". They still belong to the single Acqua row.
            water_tokens = {"acqua", "acque", "tullia", "lilia", "levissima", "leviss", "benedetto", "sanbenedetto", "santanna"}
            if item_tokens & water_tokens and "acquaragia" not in item_tokens and "acquaossigenata" not in item_tokens:
                if key and key[0].startswith("acqua "):
                    pass
                else:
                    water_type = "naturale" if item_tokens & {"naturale", "nat"} else "frizzante" if item_tokens & {"frizzante", "gassata", "gas", "friz"} else "tonica" if "tonica" in item_tokens else "acqua"
                    key = (f"acqua {water_type}", "family")
        elif key and collapse_family and key[0] == collapse_family:
            key = (collapse_family, "family")
        (groups[key] if key else passthrough).append(item)

    # A supplier/brand is often embedded in the free-text name. Merge two
    # same-content families when they share a meaningful product anchor, so
    # ``biscotti marca-a`` and ``biscotti marca-b`` are one comparison row.
    ignored_family_tokens = {
        "acqua", "bottiglia", "confezione", "confezioni", "naturale", "frizzante",
        "gassata", "gas", "nat", "pet", "pezzo", "pezzi", "prodotto", "tipo", "bev", "beve", "bevanda", "bevande",
    }

    def family_tokens(family: str) -> set[str]:
        return {
            token for token in family.split()
            if len(token) >= 5 and token not in ignored_family_tokens and not token.isdigit()
        }

    group_keys = list(groups)
    parents = list(range(len(group_keys)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left, left_key in enumerate(group_keys):
        for right in range(left + 1, len(group_keys)):
            right_key = group_keys[right]
            if left_key[1] != right_key[1]:
                continue
            common = family_tokens(left_key[0]) & family_tokens(right_key[0])
            # Package-only names need one extra shared product anchor: the
            # generic ``carta igienica`` prefix must not merge 500, bauletto
            # and fascettata into one row.
            minimum_common_tokens = 3 if left_key[1] == "package" else 2
            similarity = product_family_similarity(left_key[0], right_key[0])
            # Borrow the candidate-score idea from catalog matchers, but keep
            # a shared anchor so fuzzy similarity cannot merge unrelated
            # products that merely use the same generic word.
            if len(common) >= minimum_common_tokens or (common and similarity >= 92):
                union(left, right)

    if group_keys:
        collapsed: dict[int, list[dict]] = defaultdict(list)
        for index, key in enumerate(group_keys):
            collapsed[find(index)].extend(groups[key])
        groups = {group_keys[root]: rows for root, rows in collapsed.items()}

    def display_item(item: dict) -> dict:
        raw_name = str(item.get("nome_canonico") or "").strip()
        result = {**item, "nome_canonico": normalize_product_display_name(raw_name)}
        if raw_name and not result.get("canonical_names"):
            result["canonical_names"] = [raw_name]
        return result

    def water_display_name(key: tuple[str, str]) -> str:
        water_type = key[0].removeprefix("acqua ").title()
        if key[1] == "family":
            return f"Acqua {water_type}"
        if re.fullmatch(r"\d+(?:[.,]\d+)?x\d+", key[1]):
            return f"Acqua {water_type} {key[1]}"
        return f"Acqua {water_type} {key[1].replace('.', ',')} l"

    merged = [display_item(item) for item in passthrough]
    for key, rows in groups.items():
        if len(rows) == 1:
            single = display_item(rows[0])
            if key[0].startswith("acqua "):
                single["nome_canonico"] = water_display_name(key)
            merged.append(single)
            continue
        representative = min(rows, key=lambda row: len(str(row.get("nome_canonico") or "")))
        names = [str(row.get("nome_canonico") or "") for row in rows]
        purchases = sum(int(row.get("purchases") or 0) for row in rows)
        weighted_prices = [
            (float(row["avg_price"]), int(row.get("purchases") or 0))
            for row in rows if row.get("avg_price") is not None
        ]
        result = {**representative, "canonical_names": names, "purchases": purchases}
        prices = [float(row[field]) for row in rows for field in ("min_price", "max_price") if row.get(field) is not None]
        if prices:
            result["min_price"] = min(float(row["min_price"]) for row in rows if row.get("min_price") is not None)
            result["max_price"] = max(float(row["max_price"]) for row in rows if row.get("max_price") is not None)
        if weighted_prices:
            total_weight = sum(weight for _, weight in weighted_prices)
            result["avg_price"] = round(sum(price * weight for price, weight in weighted_prices) / total_weight, 4) if total_weight else round(sum(price for price, _ in weighted_prices) / len(weighted_prices), 4)
        result["nome_canonico"] = (
            water_display_name(key)
            if key[0].startswith("acqua ")
            else f"Acquaragia {key[1].replace('.', ',')} l"
            if key[0] == "acquaragia"
            else normalize_product_display_name(str(representative.get("nome_canonico") or "").strip())
        )
        merged.append(result)
    return sorted(merged, key=lambda item: str(item.get("nome_canonico") or ""))
