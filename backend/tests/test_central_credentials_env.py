from app.config import Settings


def test_stale_env_vars_are_ignored(monkeypatch):
    monkeypatch.setenv("EYESUPREMO_CENTRAL_PIN", "999999")
    monkeypatch.setenv("EYESUPREMO_CENTRAL_USERNAME", "altro")
    s = Settings()
    assert (s.central_username, s.central_pin) == ("supremo", "000000")


def test_explicit_override_still_possible(monkeypatch):
    monkeypatch.setenv("EYESUPREMO_CENTRAL_PIN_OVERRIDE", "123456")
    assert Settings().central_pin == "123456"


def test_empty_since_is_sent_as_null(monkeypatch):
    import asyncio
    import httpx
    from app import central_service

    seen = {}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            seen.update(json)
            return httpx.Response(200, json={"items": []}, request=httpx.Request("POST", url))

    monkeypatch.setattr(central_service.httpx, "AsyncClient", FakeClient)
    asyncio.run(central_service.central_review_page(0, 500, ""))
    assert seen["p_since"] is None
