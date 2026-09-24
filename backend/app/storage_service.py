"""Supabase adapter: blob Storage + catalogo eye_central_* (MultiHotel).

Struttura ottimale
------------------
Metadati (già in MultiHotel):
  eye_central_invoices / eye_central_invoice_rows
  RPC eye_central_invoice_page(p_username, p_pin, p_limit, p_offset, p_since)
  eye_central_reviews
  RPC eye_central_review_page(p_username, p_pin, p_limit, p_offset, p_since)

Blob (nuovi):
  bucket  eye-invoices  (privato, solo service_role)
  path    invoices/{xml|pdf|doc}/{hh}/{source_hash}{ext}
          es. invoices/xml/30/30ed1ecb27af6bd9….xml
  indice  public.eye_central_invoice_blobs  (PK = source_hash)

Il path è content-addressable: stesso hash → stesso path → dedup con x-upsert.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Literal

import httpx

from .config import settings

Kind = Literal["xml", "pdf", "doc"]


def detect_kind(original_name: str) -> Kind:
    suffix = Path(original_name).suffix.lower()
    if suffix in {".xml", ".p7m"} or original_name.lower().endswith(".xml.p7m"):
        return "xml"
    if suffix == ".pdf":
        return "pdf"
    return "doc"


def build_storage_path(original_name: str, file_hash: str, when=None) -> str:  # noqa: ARG001
    """Path stabile content-addressable: invoices/{kind}/{hh}/{hash}{ext}.

    `when` è ignorato (tenuto per compatibilità chiamate): la data non entra nel path
    così un re-upload dello stesso file non produce una seconda locazione.
    """
    digest = (file_hash or "").strip().lower()
    if len(digest) < 16:
        raise ValueError("file_hash troppo corto per path content-addressable")
    kind = detect_kind(original_name)
    ext = Path(original_name).suffix.lower()
    if original_name.lower().endswith(".xml.p7m"):
        ext = ".xml.p7m"
    elif not ext:
        ext = {"xml": ".xml", "pdf": ".pdf", "doc": ""}.get(kind, "")
    shard = digest[:2]
    root = (settings.supabase_storage_root or "invoices").strip("/")
    return f"{root}/{kind}/{shard}/{digest}{ext}"


def storage_status() -> dict:
    root = (settings.supabase_storage_root or "invoices").strip("/")
    return {
        "configured": settings.storage_configured,
        "central_configured": settings.central_configured,
        "reviews_configured": settings.reviews_configured,
        "mode": "supabase" if settings.storage_configured else "local_mirror",
        "project_ref": "ooqlfldcrnkudhgjnied",
        "bucket": settings.supabase_bucket,
        "storage_root": root,
        "index_table": "eye_central_invoice_blobs",
        "reviews_table": "eye_central_reviews",
        "url": settings.supabase_url,
        "central_gateway": settings.supabase_central_gateway,
        "location_example": f"{settings.supabase_bucket}/{root}/xml/30/<sha256>.xml",
        "message": None
        if settings.storage_configured
        else "Supabase non configurato: i file restano nel mirror locale data/supabase_mirror",
    }


def _mirror_root() -> Path:
    root = settings.data_dir / "supabase_mirror"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _rest_key() -> str:
    key = settings.supabase_rest_key
    if not key:
        raise RuntimeError("Chiave Supabase assente (service o anon)")
    return key


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    key = _rest_key()
    headers = {"Authorization": f"Bearer {key}", "apikey": key}
    if extra:
        headers.update(extra)
    return headers


def _rest_url(path: str) -> str:
    if not settings.supabase_url:
        raise RuntimeError("RANDFATTURE_SUPABASE_URL assente")
    return f"{settings.supabase_url.rstrip('/')}/{path.lstrip('/')}"


def upload_bytes(
    storage_path: str,
    content: bytes,
    content_type: str | None = None,
    *,
    file_hash: str | None = None,
    original_name: str | None = None,
    uploaded_by: str | None = None,
) -> dict:
    """Upload su Supabase Storage o mirror locale; indicizza in eye_central_invoice_blobs."""
    ctype = content_type or mimetypes.guess_type(storage_path)[0] or "application/octet-stream"
    if not settings.storage_configured:
        target = _mirror_root() / storage_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {
            "backend": "local_mirror",
            "bucket": settings.supabase_bucket,
            "path": storage_path,
            "bytes": len(content),
            "content_type": ctype,
            "indexed": False,
        }

    url = _rest_url(f"storage/v1/object/{settings.supabase_bucket}/{storage_path}")
    with httpx.Client(timeout=60) as client:
        res = client.post(
            url,
            content=content,
            headers={**_headers(), "Content-Type": ctype, "x-upsert": "true"},
        )
        res.raise_for_status()

    indexed = False
    index_error = None
    if file_hash:
        try:
            register_invoice_blob(
                source_hash=file_hash,
                source_filename=original_name or Path(storage_path).name,
                storage_path=storage_path,
                content_type=ctype,
                size_bytes=len(content),
                uploaded_by=uploaded_by,
            )
            indexed = True
        except Exception as exc:  # noqa: BLE001 — best-effort finché la migration non è applicata
            index_error = str(exc)

    out: dict[str, Any] = {
        "backend": "supabase",
        "bucket": settings.supabase_bucket,
        "path": storage_path,
        "bytes": len(content),
        "content_type": ctype,
        "indexed": indexed,
    }
    if index_error:
        out["index_error"] = index_error
    return out


def download_bytes(storage_path: str) -> bytes:
    if not settings.storage_configured:
        target = _mirror_root() / storage_path
        if not target.exists():
            raise FileNotFoundError(f"File non trovato nel mirror locale: {storage_path}")
        return target.read_bytes()

    url = _rest_url(f"storage/v1/object/{settings.supabase_bucket}/{storage_path}")
    with httpx.Client(timeout=60) as client:
        res = client.get(url, headers=_headers())
        res.raise_for_status()
        return res.content


def register_invoice_blob(
    *,
    source_hash: str,
    source_filename: str,
    storage_path: str,
    content_type: str | None,
    size_bytes: int,
    invoice_id: str | None = None,
    uploaded_by: str | None = None,
) -> dict | None:
    """Upsert su public.eye_central_invoice_blobs (PK = source_hash)."""
    if not settings.storage_configured:
        return None
    digest = source_hash.strip().lower()
    row = {
        "source_hash": digest,
        "source_filename": source_filename,
        "kind": detect_kind(source_filename),
        "storage_bucket": settings.supabase_bucket,
        "storage_path": storage_path,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "invoice_id": invoice_id,
        "uploaded_by": uploaded_by,
    }
    url = _rest_url("rest/v1/eye_central_invoice_blobs?on_conflict=source_hash")
    headers = _headers(
        {
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
    )
    with httpx.Client(timeout=30) as client:
        res = client.post(url, json=row, headers=headers)
        res.raise_for_status()
        data = res.json()
        return data[0] if isinstance(data, list) and data else data


# Alias retrocompatibile
register_invoice_file = register_invoice_blob


def _normalize_central_page(data, *, limit: int, offset: int) -> dict:
    if not isinstance(data, dict):
        return {"items": data if isinstance(data, list) else [], "limit": limit, "offset": offset, "total": None}
    # Alcuni gateway wrappano in {data:{...}} o {result:{...}}
    for key in ("data", "result", "payload", "page"):
        inner = data.get(key)
        if isinstance(inner, dict) and ("items" in inner or "rows" in inner):
            data = inner
            break
    items = data.get("items")
    if items is None:
        items = data.get("rows")
    if items is None and isinstance(data.get("invoices"), list):
        items = data["invoices"]
    if not isinstance(items, list):
        items = []
    return {
        "items": items,
        "total": data.get("total"),
        "limit": data.get("limit", limit),
        "offset": data.get("offset", offset),
    }


def _central_via_gateway(
    *,
    limit: int,
    offset: int,
    since: str | None,
    username: str,
    pin: str,
) -> dict:
    gateway = (settings.supabase_central_gateway or "").strip().rstrip("/")
    if not gateway:
        raise RuntimeError("Gateway centrale non configurato")
    action = (settings.supabase_central_gateway_action or "invoice_page").strip()
    body = {
        "action": action,
        "username": username,
        "pin": pin,
        "limit": limit,
        "offset": offset,
        "p_username": username,
        "p_pin": pin,
        "p_limit": limit,
        "p_offset": offset,
        "p_since": since,
    }
    headers = {"Content-Type": "application/json"}
    if settings.supabase_rest_key:
        headers["apikey"] = settings.supabase_rest_key
        headers["Authorization"] = f"Bearer {settings.supabase_rest_key}"
    with httpx.Client(timeout=60) as client:
        res = client.post(gateway, json=body, headers=headers)
        if res.status_code >= 400:
            detail = res.text
            try:
                detail = res.json().get("error") or res.text
            except Exception:
                pass
            raise RuntimeError(f"Gateway centrale ({res.status_code}): {detail}")
        data = res.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data["error"]))
    return _normalize_central_page(data, limit=limit, offset=offset)


def _central_via_rpc(
    *,
    limit: int,
    offset: int,
    since: str | None,
    username: str,
    pin: str,
) -> dict:
    body = {
        "p_username": username,
        "p_pin": pin,
        "p_limit": limit,
        "p_offset": offset,
        "p_since": since,
    }
    url = _rest_url("rest/v1/rpc/eye_central_invoice_page")
    with httpx.Client(timeout=60) as client:
        res = client.post(url, json=body, headers=_headers({"Content-Type": "application/json"}))
        res.raise_for_status()
        data = res.json()
    return _normalize_central_page(data, limit=limit, offset=offset)


def central_invoice_page(
    *,
    limit: int = 50,
    offset: int = 0,
    since: str | None = None,
    username: str | None = None,
    pin: str | None = None,
) -> dict:
    """Catalogo metadati MultiHotel: Edge gateway (preferito) oppure RPC."""
    user = username or settings.supabase_central_username
    secret = pin or settings.supabase_central_pin
    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))
    if not secret:
        raise RuntimeError(
            "Catalogo centrale non configurato: serve RANDFATTURE_SUPABASE_CENTRAL_PIN"
        )
    if settings.supabase_central_gateway:
        try:
            return _central_via_gateway(
                limit=lim, offset=off, since=since, username=user, pin=secret
            )
        except Exception as gateway_exc:
            # Fallback RPC se gateway fallisce e abbiamo chiave REST
            if settings.supabase_url and settings.supabase_rest_key:
                try:
                    return _central_via_rpc(
                        limit=lim, offset=off, since=since, username=user, pin=secret
                    )
                except Exception:
                    raise gateway_exc from None
            raise
    if not (settings.supabase_url and settings.supabase_rest_key):
        raise RuntimeError(
            "Catalogo centrale non configurato: gateway oppure URL+chiave Supabase"
        )
    return _central_via_rpc(limit=lim, offset=off, since=since, username=user, pin=secret)


def _central_review_via_gateway(
    *,
    limit: int,
    offset: int,
    since: str | None,
    username: str,
    pin: str,
) -> dict:
    gateway = (settings.supabase_central_gateway or "").strip().rstrip("/")
    if not gateway:
        raise RuntimeError("Gateway centrale non configurato")
    body = {
        "action": "review_page",
        "username": username,
        "pin": pin,
        "limit": limit,
        "offset": offset,
        "p_username": username,
        "p_pin": pin,
        "p_limit": limit,
        "p_offset": offset,
        "p_since": since,
    }
    headers = {"Content-Type": "application/json"}
    if settings.supabase_rest_key:
        headers["apikey"] = settings.supabase_rest_key
        headers["Authorization"] = f"Bearer {settings.supabase_rest_key}"
    with httpx.Client(timeout=60) as client:
        res = client.post(gateway, json=body, headers=headers)
        if res.status_code >= 400:
            detail = res.text
            try:
                detail = res.json().get("error") or res.text
            except Exception:
                pass
            raise RuntimeError(f"Gateway recensioni ({res.status_code}): {detail}")
        data = res.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data["error"]))
    return _normalize_central_page(data, limit=limit, offset=offset)


def _central_review_via_rpc(
    *,
    limit: int,
    offset: int,
    since: str | None,
    username: str,
    pin: str,
) -> dict:
    body = {
        "p_username": username,
        "p_pin": pin,
        "p_limit": limit,
        "p_offset": offset,
        "p_since": since,
    }
    url = _rest_url("rest/v1/rpc/eye_central_review_page")
    with httpx.Client(timeout=60) as client:
        res = client.post(url, json=body, headers=_headers({"Content-Type": "application/json"}))
        if res.status_code >= 400:
            detail = res.text
            try:
                detail = res.json().get("message") or res.json().get("error") or res.text
            except Exception:
                pass
            raise RuntimeError(f"RPC eye_central_review_page ({res.status_code}): {detail}")
        data = res.json()
    return _normalize_central_page(data, limit=limit, offset=offset)


def central_review_page(
    *,
    limit: int = 200,
    offset: int = 0,
    since: str | None = None,
    username: str | None = None,
    pin: str | None = None,
) -> dict:
    """Catalogo recensioni MultiHotel (eye_central_reviews via RPC, gateway opzionale)."""
    user = username or settings.supabase_central_username
    secret = pin or settings.supabase_central_pin
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    if not secret:
        raise RuntimeError(
            "Recensioni centrali non configurate: serve RANDFATTURE_SUPABASE_CENTRAL_PIN"
        )
    if not (settings.supabase_url and settings.supabase_rest_key):
        # Prova comunque il gateway se presente (alcuni deploy espongono review_page)
        if settings.supabase_central_gateway:
            return _central_review_via_gateway(
                limit=lim, offset=off, since=since, username=user, pin=secret
            )
        raise RuntimeError(
            "Recensioni centrali non configurate: URL + chiave Supabase (anon o service)"
        )
    if settings.supabase_central_gateway:
        try:
            return _central_review_via_gateway(
                limit=lim, offset=off, since=since, username=user, pin=secret
            )
        except Exception:
            pass
    return _central_review_via_rpc(
        limit=lim, offset=off, since=since, username=user, pin=secret
    )


# Codici hotel MultiHotel ↔ sezioni UI Eye
HOTEL_CODE_ALIASES: dict[str, str] = {
    "gio": "hotelgio",
    "hotelgio": "hotelgio",
    "choco": "chocohotel",
    "chocohotel": "chocohotel",
    "brigantino": "brigantino",
    "ilbrigantino": "brigantino",
}

HOTEL_LABELS: dict[str, dict[str, str]] = {
    "hotelgio": {"name": "Hotel Giò", "short": "Hotel Giò"},
    "chocohotel": {"name": "Chocohotel", "short": "Chocohotel"},
    "brigantino": {"name": "Hotel Il Brigantino", "short": "Il Brigantino"},
}


def normalize_hotel_code(code: str | None) -> str:
    raw = (code or "").strip().lower()
    return HOTEL_CODE_ALIASES.get(raw, raw or "unknown")


def normalize_rating(value) -> tuple[float | None, float | None]:
    """Restituisce (stelle_0_5, raw) ignorando outlier (>10, tipici digest Booking)."""
    try:
        raw = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None, None
    if raw is None:
        return None, None
    if 0 < raw <= 5:
        return raw, raw
    if 5 < raw <= 10:
        return round(raw / 2, 2), raw
    return None, raw


def _serialize_central_review(item: dict[str, Any], index: int) -> dict[str, Any]:
    hotel_ui = normalize_hotel_code(item.get("hotel_code"))
    stars, raw = normalize_rating(item.get("rating"))
    author = (item.get("author") or "").strip() or "Ospite"
    if author.startswith("<") and author.endswith(">"):
        author = author[1:-1]
    return {
        "id": item.get("sync_uuid") or f"r-{index}",
        "sync_uuid": item.get("sync_uuid"),
        "hotelId": hotel_ui,
        "hotel_code": item.get("hotel_code"),
        "author": author,
        "source": item.get("source") or "—",
        "rating": stars if stars is not None else 0,
        "rating_raw": raw,
        "rating_missing": stars is None,
        "date": item.get("review_date") or "",
        "text": item.get("text") or "",
        "room_code": item.get("room_code"),
        "status": "Importata",
        "updated_at": item.get("updated_at"),
    }


def central_reviews_catalog(
    *,
    hotel_code: str | None = None,
    q: str = "",
    limit: int = 2000,
    username: str | None = None,
    pin: str | None = None,
) -> dict[str, Any]:
    """Scarica (paginando) le recensioni centrali e aggrega i KPI per hotel."""
    page_size = 200
    collected: list[dict[str, Any]] = []
    offset = 0
    reported_total: int | None = None
    max_items = max(1, min(int(limit), 5000))

    while len(collected) < max_items:
        page = central_review_page(
            limit=page_size,
            offset=offset,
            username=username,
            pin=pin,
        )
        batch = page.get("items") or []
        if reported_total is None and page.get("total") is not None:
            reported_total = int(page["total"])
        if not batch:
            break
        collected.extend(batch)
        offset += len(batch)
        if reported_total is not None and offset >= reported_total:
            break
        if len(batch) < page_size:
            break

    hotel_filter = normalize_hotel_code(hotel_code) if hotel_code and hotel_code != "all" else None
    query = (q or "").strip().lower()

    serialized = [_serialize_central_review(item, i) for i, item in enumerate(collected)]
    if hotel_filter:
        serialized = [r for r in serialized if r["hotelId"] == hotel_filter]
    if query:
        serialized = [
            r
            for r in serialized
            if query in f"{r['author']} {r['text']} {r['source']} {r.get('room_code') or ''}".lower()
        ]

    # KPI su tutto il catalogo scaricato (prima del filtro testo), per hotel
    by_hotel: dict[str, list[dict[str, Any]]] = {hid: [] for hid in HOTEL_LABELS}
    for item in collected:
        hid = normalize_hotel_code(item.get("hotel_code"))
        by_hotel.setdefault(hid, []).append(item)

    def _hotel_stats(hid: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        label = HOTEL_LABELS.get(hid, {"name": hid, "short": hid})
        ratings = []
        for row in rows:
            stars, _raw = normalize_rating(row.get("rating"))
            if stars is not None:
                ratings.append(stars)
        avg = round(sum(ratings) / len(ratings), 2) if ratings else None
        return {
            "id": hid,
            "name": label["name"],
            "short": label["short"],
            "count": len(rows),
            "score": f"{avg:.2f}" if avg is not None else "—",
            "avg_rating": avg,
        }

    hotels = [
        {
            "id": "all",
            "name": "Tutti gli hotel",
            "short": "Tutti",
            "count": len(collected),
            "score": "—",
            "avg_rating": None,
        }
    ]
    for hid in ("hotelgio", "chocohotel", "brigantino"):
        hotels.append(_hotel_stats(hid, by_hotel.get(hid, [])))

    all_ratings = []
    for row in collected:
        stars, _raw = normalize_rating(row.get("rating"))
        if stars is not None:
            all_ratings.append(stars)
    if all_ratings:
        hotels[0]["avg_rating"] = round(sum(all_ratings) / len(all_ratings), 2)
        hotels[0]["score"] = f"{hotels[0]['avg_rating']:.2f}"

    return {
        "configured": True,
        "total": reported_total if reported_total is not None else len(collected),
        "returned": len(serialized),
        "items": serialized,
        "hotels": hotels,
        "sources": sorted({str(i.get("source") or "") for i in collected if i.get("source")}),
    }


def resolve_blob_path(source_hash: str, kind: Kind | None = None, ext: str = ".xml") -> str:
    """Calcola il path atteso per un hash noto (senza I/O)."""
    name = f"{source_hash}{ext}"
    if kind == "pdf":
        name = f"{source_hash}.pdf"
    elif kind == "doc":
        name = source_hash
    return build_storage_path(name, source_hash)
