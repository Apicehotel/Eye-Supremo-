import httpx
from rapidfuzz import fuzz

from .config import settings


def configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_publishable_key and settings.central_username and settings.central_pin)


async def central_invoice_search(query: str = "", limit: int = 50) -> dict:
    if not configured():
        return {"enabled": False, "items": [], "message": "Supabase centrale non configurato"}
    url = settings.supabase_url.rstrip("/") + f"/functions/v1/{settings.central_function}"
    payload = {"action": "search_invoices", "username": settings.central_username, "pin": settings.central_pin, "query": query, "limit": max(1, min(limit, 500))}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
            response.raise_for_status()
            data = response.json()
        items = data.get("items", []) if isinstance(data, dict) else []
        if not items and query.strip() and len(query.strip()) >= 3:
            # Retry against a short prefix, then rank the candidates locally.
            # This handles small typing errors without broadening a product
            # search into a dangerous substring match (e.g. bomboloni/bombole).
            prefix = query.strip()[:2]
            async with httpx.AsyncClient(timeout=20) as retry_client:
                broad = await retry_client.post(url, json={**payload, "query": prefix, "limit": 500}, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
            if broad.is_success:
                candidates = broad.json().get("items", []) if isinstance(broad.json(), dict) else []
                ranked = []
                needle = query.strip().lower()
                for item in candidates:
                    fields = [str(item.get(k) or "").lower() for k in ("original_description", "normalized_description", "supplier_name")]
                    score = max((fuzz.WRatio(needle, field) for field in fields if field and len(field) >= len(needle) * .75), default=0)
                    if score >= 70:
                        ranked.append((score, item))
                items = [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:max(1, min(limit, 500))]]
        return {"enabled": True, "items": items, "count": len(items)}
    except Exception as exc:
        return {"enabled": True, "items": [], "message": str(exc)}


async def central_invoice_page(offset: int = 0, limit: int = 500, since: str | None = None) -> dict:
    if not configured(): return {"enabled": False, "items": [], "total": 0}
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/eye_central_invoice_page"
    payload = {"p_username": settings.central_username, "p_pin": settings.central_pin, "p_offset": max(0, offset), "p_limit": max(1, min(limit, 500)), "p_since": since}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
        if response.is_success:
            return response.json()
        # Older Supabase projects may have the RPC deployed without the anon
        # execute grant. The gateway is already authenticated and exposes the
        # same central search view, so use it as a safe compatibility fallback.
        if response.status_code in {401, 403}:
            fallback = await central_invoice_search("", min(limit, 500))
            flat_items = fallback.get("items", [])
            grouped: dict[str, dict] = {}
            for row in flat_items:
                key = str(row.get("source_hash") or row.get("id"))
                invoice = grouped.setdefault(key, {
                    "id": row.get("id"), "source_hash": row.get("source_hash"),
                    "source_filename": row.get("source_filename"), "invoice_number": row.get("invoice_number"),
                    "invoice_date": row.get("invoice_date"), "taxable": row.get("taxable", 0),
                    "vat": row.get("vat", 0), "total": row.get("total", 0), "currency": row.get("currency", "EUR"),
                    "destination_hotel": row.get("destination_hotel"), "supplier_name": row.get("supplier_name"), "rows": [],
                })
                if row.get("original_description") is not None:
                    invoice["rows"].append({
                        "original_description": row.get("original_description"),
                        "normalized_description": row.get("normalized_description"),
                        "quantity": row.get("quantity"), "unit_price": row.get("unit_price"),
                        "line_total": row.get("line_total"), "analysis_status": row.get("analysis_status"),
                    })
            return {"items": list(grouped.values()), "offset": offset, "limit": limit, "total": len(grouped), "fallback": True}
        response.raise_for_status()


async def central_review_upsert(review: dict) -> dict:
    if not configured(): return {"enabled": False, "synced": False}
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/eye_central_review_upsert"
    payload = {"p_username": settings.central_username, "p_pin": settings.central_pin, "p_review": review}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
        response.raise_for_status()
        return {"enabled": True, "synced": True, "remote": response.json()}


async def central_review_page(offset: int = 0, limit: int = 500, since: str | None = None) -> dict:
    if not configured(): return {"enabled": False, "items": [], "total": 0}
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/eye_central_review_page"
    payload = {"p_username": settings.central_username, "p_pin": settings.central_pin, "p_offset": max(0, offset), "p_limit": max(1, min(limit, 500)), "p_since": since}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Authorization": f"Bearer {settings.supabase_publishable_key or ''}", "Content-Type": "application/json"})
        response.raise_for_status()
        return response.json()


async def central_invoice_upsert(*, source_hash: str, source_filename: str, supplier: dict, invoice: dict, rows: list[dict]) -> dict:
    if not configured():
        return {"enabled": False, "synced": False, "message": "Supabase centrale non configurato"}
    url = settings.supabase_url.rstrip("/") + f"/functions/v1/{settings.central_function}"
    payload = {"action": "upsert_invoice", "username": settings.central_username, "pin": settings.central_pin,
               "source_hash": source_hash, "source_filename": source_filename, "supplier": supplier, "invoice": invoice, "rows": rows}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
            response.raise_for_status()
        return {"enabled": True, "synced": True, "remote": response.json() if response.content else {}}
    except Exception as exc:
        return {"enabled": True, "synced": False, "message": str(exc)}


async def central_invoice_detail(source_hash: str) -> dict:
    if not configured():
        return {"enabled": False, "items": []}
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/eye_central_invoice_detail"
    payload = {"p_username": settings.central_username, "p_pin": settings.central_pin, "p_source_hash": source_hash}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
        response.raise_for_status()
        return response.json()


async def central_product_summary() -> dict:
    if not configured():
        return {"enabled": False, "product_rows": 0, "distinct_products": 0}
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/eye_central_product_summary"
    payload = {"p_username": settings.central_username, "p_pin": settings.central_pin}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
    return {"enabled": True, **(data if isinstance(data, dict) else {})}


async def central_product_page(query: str = "", limit: int = 200) -> dict:
    if not configured():
        return {"enabled": False, "items": [], "total": 0, "message": "Supabase centrale non configurato"}
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/eye_central_product_page"
    payload = {"p_username": settings.central_username, "p_pin": settings.central_pin, "p_query": query, "p_limit": max(1, min(limit, 2000))}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
    return {"enabled": True, **(data if isinstance(data, dict) else {})}


async def central_product_detail(canonical_name: str) -> dict:
    if not configured():
        return {"enabled": False, "product": None, "history": []}
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/eye_central_product_detail"
    payload = {"p_username": settings.central_username, "p_pin": settings.central_pin, "p_canonical_name": canonical_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, dict) else {"product": None, "history": []}


async def central_supplier_page(query: str = "", limit: int = 200) -> dict:
    if not configured():
        return {"enabled": False, "items": [], "total": 0, "message": "Supabase centrale non configurato"}
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/eye_central_supplier_page"
    payload = {"p_username": settings.central_username, "p_pin": settings.central_pin, "p_query": query, "p_limit": max(1, min(limit, 2000))}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
    return {"enabled": True, **(data if isinstance(data, dict) else {"items": []})}


async def central_supplier_detail(supplier_id: str) -> dict:
    if not configured():
        return {"enabled": False, "supplier": None, "invoices": [], "categories": []}
    url = settings.supabase_url.rstrip("/") + "/rest/v1/rpc/eye_central_supplier_detail"
    payload = {"p_username": settings.central_username, "p_pin": settings.central_pin, "p_supplier_id": supplier_id}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=payload, headers={"apikey": settings.supabase_publishable_key or "", "Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, dict) else {"supplier": None, "invoices": [], "categories": []}
