"""Compatibility facade for the first public API version."""
from __future__ import annotations

API_V1_PREFIX = "/api/v1"


def legacy_path(path: str) -> str | None:
    if path == API_V1_PREFIX:
        return "/api"
    if path.startswith(API_V1_PREFIX + "/"):
        return "/api" + path[len(API_V1_PREFIX):]
    return None
