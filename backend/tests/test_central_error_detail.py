import httpx
import pytest

from app.central_service import _check


def test_check_includes_server_message():
    req = httpx.Request("POST", "https://x.supabase.co/rest/v1/rpc/eye_central_invoice_page")
    resp = httpx.Response(400, json={"message": "Credenziali non valide", "code": "P0001"}, request=req)
    with pytest.raises(httpx.HTTPStatusError) as exc:
        _check(resp)
    assert "Credenziali non valide" in str(exc.value)
    assert "eye_central_invoice_page" in str(exc.value)
    assert "400" in str(exc.value)


def test_check_ok_passes():
    req = httpx.Request("POST", "https://x.supabase.co/rest/v1/rpc/a")
    _check(httpx.Response(200, json={}, request=req))
