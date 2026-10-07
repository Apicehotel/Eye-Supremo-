"""Layer mirror IA locale per PC ufficio.

Layer 0 — deterministico (SQLite): calcoli e retrieval, sempre.
Layer 1 — fast mirror (es. llama3.2:3b): sintesi veloce di default.
Layer 2 — quality (es. qwen3:8b): solo se il veloce fallisce o ha confidenza bassa.

Policy:
  fast_first — default ufficio: prova il veloce, scala alla qualità se serve
  fast_only  — mai scalare (PC più deboli)
  quality    — usa sempre il modello qualità se disponibile
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

POLICIES = ("fast_first", "fast_only", "quality")


@dataclass(frozen=True)
class AiRuntime:
    ollama_url: str
    chat_model_fast: str
    chat_model_quality: str
    embedding_model: str
    policy: str


def resolve_ai_runtime(db: Session | None = None) -> AiRuntime:
    stored: dict[str, str] = {}
    if db is not None:
        stored = {x.key: x.value for x in db.scalars(select(AppSetting)).all()}
    policy = (stored.get("ai_layer_policy") or settings.ai_layer_policy or "fast_first").strip().lower()
    if policy not in POLICIES:
        policy = "fast_first"
    return AiRuntime(
        ollama_url=(stored.get("ollama_url") or settings.ollama_url).rstrip("/"),
        chat_model_fast=(stored.get("chat_model_fast") or settings.chat_model_fast).strip(),
        chat_model_quality=(stored.get("chat_model") or settings.chat_model).strip(),
        embedding_model=(stored.get("embedding_model") or settings.embedding_model).strip(),
        policy=policy,
    )


def normalize_model_name(name: str) -> str:
    return name.strip().lower()


def is_model_present(installed: Iterable[str], wanted: str) -> bool:
    target = normalize_model_name(wanted)
    if not target:
        return False
    names = {normalize_model_name(x) for x in installed}
    if target in names:
        return True
    # Ollama a volte espone "modello:tag" e "modello:latest" equivalenti
    if ":" not in target:
        return any(n == target or n.startswith(target + ":") for n in names)
    base, tag = target.split(":", 1)
    if tag == "latest":
        return any(n == base or n.startswith(base + ":") for n in names)
    return False


def pick_model_sequence(runtime: AiRuntime, installed: Iterable[str]) -> list[tuple[str, str]]:
    """Restituisce [(layer, model), ...] nell'ordine di tentativo."""
    installed_list = list(installed)
    fast = runtime.chat_model_fast
    quality = runtime.chat_model_quality
    fast_ok = is_model_present(installed_list, fast)
    quality_ok = is_model_present(installed_list, quality)

    if runtime.policy == "quality":
        if quality_ok:
            return [("quality", quality)]
        if fast_ok:
            return [("fast", fast)]
        return []

    if runtime.policy == "fast_only":
        if fast_ok:
            return [("fast", fast)]
        if quality_ok:
            return [("quality", quality)]
        return []

    # fast_first
    seq: list[tuple[str, str]] = []
    if fast_ok:
        seq.append(("fast", fast))
    if quality_ok and normalize_model_name(quality) != normalize_model_name(fast):
        seq.append(("quality", quality))
    elif quality_ok and not seq:
        seq.append(("quality", quality))
    return seq


def should_escalate(structured: dict[str, Any], *, has_more: bool, policy: str) -> bool:
    if not has_more or policy != "fast_first":
        return False
    answer = str(structured.get("answer", "")).strip()
    confidence = str(structured.get("confidence", "medium")).lower()
    return (not answer) or confidence == "low"


async def fetch_installed_models(ollama_url: str, timeout: float = 2.0) -> list[str]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{ollama_url}/api/tags")
        response.raise_for_status()
        return [m.get("name", "") for m in response.json().get("models", []) if m.get("name")]


async def generate_with_layers(
    *,
    prompt: str,
    runtime: AiRuntime,
    response_format: dict[str, Any] | None = None,
    temperature: float = 0.0,
    num_predict: int = 650,
    request_timeout: float = 60.0,
) -> dict[str, Any]:
    """Chiama Ollama rispettando i layer. Restituisce JSON + meta _layer/_model."""
    installed = await fetch_installed_models(runtime.ollama_url)
    sequence = pick_model_sequence(runtime, installed)
    if not sequence:
        raise RuntimeError("Nessun modello chat disponibile in Ollama")

    last_error: Exception | None = None
    for index, (layer, model) in enumerate(sequence):
        has_more = index < len(sequence) - 1
        predict = 420 if layer == "fast" else num_predict
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": predict},
        }
        if response_format is not None:
            payload["format"] = response_format
        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                res = await client.post(f"{runtime.ollama_url}/api/generate", json=payload)
                res.raise_for_status()
                raw = res.json().get("response", "")
            if response_format is not None:
                structured = json.loads(raw or "{}")
                if not isinstance(structured, dict):
                    raise ValueError("Risposta non oggetto JSON")
                if should_escalate(structured, has_more=has_more, policy=runtime.policy):
                    last_error = ValueError("Confidenza bassa sul layer veloce")
                    continue
                structured["_layer"] = layer
                structured["_model"] = model
                return structured
            text = str(raw or "").strip()
            if not text and has_more:
                last_error = ValueError("Risposta vuota sul layer veloce")
                continue
            return {"answer": text, "_layer": layer, "_model": model}
        except Exception as exc:  # noqa: BLE001 — fallback controllato ai layer successivi
            last_error = exc
            if not has_more:
                break
            continue
    raise last_error or RuntimeError("Generazione IA fallita")


def layer_status_payload(installed: list[str], runtime: AiRuntime) -> dict[str, Any]:
    sequence = pick_model_sequence(runtime, installed)
    return {
        "policy": runtime.policy,
        "fast_model": runtime.chat_model_fast,
        "quality_model": runtime.chat_model_quality,
        "fast_available": is_model_present(installed, runtime.chat_model_fast),
        "quality_available": is_model_present(installed, runtime.chat_model_quality),
        "active_sequence": [{"layer": layer, "model": model} for layer, model in sequence],
    }
