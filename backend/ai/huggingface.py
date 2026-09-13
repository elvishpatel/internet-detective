"""Resilient hosted AI verification via Hugging Face's OpenAI-compatible router.

Why this module is defensive
----------------------------
Hugging Face's router does not host models itself; it forwards each request to
whichever third-party provider currently serves that repo, and those mappings
change without notice. Together, for example, retired the serverless build of
``Qwen/Qwen2.5-7B-Instruct`` (it now resolves to a dedicated-endpoint-only
``...-Turbo`` variant) and started answering with::

    400 {"error": {"code": "model_not_available", ...}}

A verifier pinned to one hardcoded model therefore dies the moment a provider
reshuffles its catalogue, and no environment-variable value can revive it.

So this module never trusts a single model. It asks the router which models are
actually live for the caller's token, builds an ordered plan of
``model:provider`` attempts, and cascades through them until one answers. The
first combination that works is remembered so later cases skip the cascade.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx

from backend.config import settings

ROUTER_BASE = "https://router.huggingface.co/v1"
CHAT_URL = f"{ROUTER_BASE}/chat/completions"
MODELS_URL = f"{ROUTER_BASE}/models"

# Small, widely-served instruct models, cheapest first. These are only seeds:
# anything the router reports as dead is dropped before a request is spent, and
# if every seed is gone the planner sweeps the live catalogue for a replacement.
DEFAULT_MODELS: tuple[str, ...] = (
    "Qwen/Qwen2.5-7B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen3-8B",
    "google/gemma-2-2b-it",
    "HuggingFaceTB/SmolLM3-3B",
    "microsoft/Phi-3.5-mini-instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
)

# Substrings that mark a repo as a chat/instruct model, and ones that mark it as
# something the verifier cannot use (embeddings, audio, image, safety filters).
_CHATTY = ("instruct", "-it", "chat", "-hf")
_NOT_CHAT = (
    "embed", "rerank", "whisper", "diffusion", "flux", "-vl", "vision", "guard",
    "bge-", "clip", "tts", "-sd", "sdxl", "moderation", "reward", "coder",
)


class AIUnavailableError(RuntimeError):
    """Raised when a required verifier cannot safely review a completed case."""


class AIConfigurationError(AIUnavailableError):
    """Raised when trying a different model cannot possibly help.

    Bad token, missing inference scope, or exhausted credits. Cascading further
    would just burn requests against the same wall, so the planner stops.
    """


class _TryNextModel(Exception):
    """Internal signal: this model/provider pair failed, but another may work."""


# --------------------------------------------------------------------------
# Live-catalogue discovery (cached, best-effort)
# --------------------------------------------------------------------------

_catalog_lock = asyncio.Lock()
_catalog: dict[str, list[str]] = {}
_catalog_fetched_at: float = 0.0
_last_good_model: str | None = None


def _split_list(raw: str | None) -> list[str]:
    return [part.strip() for part in re.split(r"[,\n]", raw or "") if part.strip()]


def _providers_of(entry: dict[str, Any], inline_provider: str) -> list[str]:
    """Pull live provider slugs out of one catalogue entry, shape-agnostically."""
    names: list[str] = []
    if inline_provider:
        names.append(inline_provider)
    raw = entry.get("providers") or entry.get("inferenceProviderMapping") or []
    if isinstance(raw, dict):
        raw = [
            {**value, "provider": value.get("provider", key)} if isinstance(value, dict) else {"provider": key}
            for key, value in raw.items()
        ]
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                status = str(item.get("status", "live")).lower()
                if status not in ("live", "active", "ok", "available", ""):
                    continue
                name = item.get("provider") or item.get("name") or item.get("provider_id")
                if isinstance(name, str) and name:
                    names.append(name)
    return names


async def _fetch_catalog(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, list[str]]:
    """Map each live model repo to the providers currently serving it."""
    response = await client.get(MODELS_URL, headers=headers)
    response.raise_for_status()
    payload = response.json()
    entries = payload.get("data") if isinstance(payload, dict) else payload
    mapping: dict[str, list[str]] = {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        raw_id = entry.get("id") or entry.get("model") or ""
        if not isinstance(raw_id, str) or not raw_id:
            continue
        base, _, inline = raw_id.partition(":")
        providers = mapping.setdefault(base, [])
        for provider in _providers_of(entry, inline):
            if provider not in providers:
                providers.append(provider)
    return mapping


async def catalog(client: httpx.AsyncClient, headers: dict[str, str], force: bool = False) -> dict[str, list[str]]:
    """Cached view of the router catalogue. Discovery is never a hard dependency."""
    global _catalog, _catalog_fetched_at
    if not settings.huggingface_discover_models:
        return {}
    async with _catalog_lock:
        age = time.monotonic() - _catalog_fetched_at
        if _catalog and not force and age < settings.huggingface_catalog_ttl:
            return _catalog
        try:
            _catalog = await _fetch_catalog(client, headers)
            _catalog_fetched_at = time.monotonic()
        except Exception:
            # If discovery fails we fall back to blind cascading, which still works.
            _catalog = _catalog or {}
        return _catalog


# --------------------------------------------------------------------------
# Attempt planning
# --------------------------------------------------------------------------

def _rough_size(model_id: str) -> float:
    """Approximate parameter count so small, cheap verifiers are tried first."""
    match = re.search(r"(\d+(?:\.\d+)?)b(?![a-z0-9])", model_id.lower())
    return float(match.group(1)) if match else 999.0


def _configured_models() -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for name in [settings.huggingface_model, *_split_list(settings.huggingface_model_fallbacks), *DEFAULT_MODELS]:
        name = (name or "").strip()
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _sweep(live: dict[str, list[str]], skip_bases: set[str], limit: int = 4) -> list[str]:
    """Self-healing: pick live instruct models nobody hardcoded, smallest first."""
    pool = []
    for base in live:
        lower = base.lower()
        if base in skip_bases or not live.get(base):
            continue
        if any(bad in lower for bad in _NOT_CHAT):
            continue
        if not any(good in lower for good in _CHATTY):
            continue
        pool.append(base)
    pool.sort(key=lambda name: (_rough_size(name), name))
    return pool[:limit]


def plan_attempts(live: dict[str, list[str]] | None = None) -> list[str]:
    """Build the ordered list of ``model`` / ``model:provider`` ids to try."""
    live = live or {}
    pinned = (settings.huggingface_provider or "").strip()
    if pinned.lower() in ("", "auto", "none", "router"):
        pinned = ""

    attempts: list[str] = []
    seen: set[str] = set()
    queued_bases: set[str] = set()

    def add(value: str) -> None:
        if value and value not in seen:
            seen.add(value)
            attempts.append(value)

    def expand(base: str) -> None:
        queued_bases.add(base)
        providers = live.get(base) or []
        # The router knows this repo and says nothing serves it: don't spend a request.
        if live and not providers:
            return
        if pinned and (not providers or pinned in providers):
            add(f"{base}:{pinned}")
        for provider in providers[:2]:
            if provider != pinned:
                add(f"{base}:{provider}")
        add(base)  # let the router choose for itself as a last resort

    for model in _configured_models():
        base, _, inline = model.partition(":")
        if inline:
            add(model)  # an explicit pair the operator chose: honour it verbatim
            queued_bases.add(base)
        else:
            expand(base)

    for base in _sweep(live, queued_bases):
        expand(base)

    # Blind tail: if discovery returned a partial or oddly-shaped catalogue we may
    # have filtered out something that actually works, so always leave a couple of
    # unqualified attempts at the end and let the router decide.
    for model in _configured_models()[:3]:
        add(model.partition(":")[0])

    return attempts[: max(1, settings.huggingface_max_attempts)]


# --------------------------------------------------------------------------
# Error classification
# --------------------------------------------------------------------------

def terse(detail: str) -> str:
    """Reduce a provider error body to its human-readable message."""
    try:
        parsed = json.loads(detail)
    except Exception:
        return " ".join(detail.split())[:200]
    message = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(message, dict):
        message = message.get("message")
    if not isinstance(message, str):
        message = parsed.get("message") if isinstance(parsed, dict) else None
    if isinstance(message, str) and message:
        return " ".join(message.split())[:200]
    return " ".join(detail.split())[:200]


def should_try_next(status: int, body: str) -> bool:
    """True when a *different* model might still succeed."""
    text = body.lower()
    if status == 401:
        return False
    # Exhausted credits look like a model error but are an account wall: cascading
    # further just burns requests. Match the wording narrowly so an unrelated
    # mention of "credit" in a model error does not abort the whole plan.
    out_of_credit = "credit" in text and any(
        word in text for word in ("exceed", "insufficient", "exhaust", "quota", "run out", "upgrade")
    )
    if status == 402 or out_of_credit or "payment required" in text:
        return False
    if status == 403:
        # A gated repo is a per-model problem; a token missing the inference
        # scope is not, and no amount of cascading will fix it.
        return any(word in text for word in ("gated", "awaiting", "accept", "license", "terms"))
    return True


# --------------------------------------------------------------------------
# Provider
# --------------------------------------------------------------------------

def build_prompt(claim: str, evidence: list[dict[str, Any]], score: dict[str, Any]) -> str:
    ledger = "\n\n".join(
        f"EVIDENCE {i + 1}\nSTANCE: {item['stance']}\nSOURCE: {item['source_title']} ({item['source_url']})\nEXCERPT: {item['excerpt']}"
        for i, item in enumerate(evidence[:10])
    ) or "No qualifying excerpts were extracted."
    return f"""You are the required verification pass for an evidence investigation.
Use only the supplied evidence ledger. Never invent facts, sources, URLs, dates, or quotes.

CLAIM: {claim}
DETERMINISTIC SCORE: {score['confidence']}/100 ({score['label']})

{ledger}

Respond in 2-5 concise sentences: say whether the verdict overstates the supplied evidence, identify the strongest support and strongest limitation, and state whether any excerpt was misclassified. Do not give a new numeric score."""


async def chat_once(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    model_id: str,
    messages: list[dict[str, str]],
) -> str:
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 300,
        "stream": False,
    }
    try:
        response = await client.post(CHAT_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise _TryNextModel(f"network error ({exc.__class__.__name__})") from exc

    if response.status_code >= 400:
        body = response.text[:2000]
        message = terse(body)
        if should_try_next(response.status_code, body):
            raise _TryNextModel(f"HTTP {response.status_code} - {message}")
        raise AIConfigurationError(
            f"Hugging Face rejected the request with HTTP {response.status_code}: {message} "
            "This is an account problem, not a model problem. Check that HUGGINGFACE_API_KEY is a "
            "fine-grained token with the 'Make calls to Inference Providers' permission and that "
            "your monthly inference credits are not exhausted."
        )

    try:
        data = response.json()
        note = (data["choices"][0]["message"]["content"] or "").strip()
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise _TryNextModel(f"unreadable response ({exc.__class__.__name__})") from exc
    if not note:
        raise _TryNextModel("model returned an empty review")
    return note


class HuggingFaceProvider:
    name = "Hugging Face Inference Providers"
    endpoint = CHAT_URL

    async def review_conclusion(self, claim, evidence, score):
        global _last_good_model

        if not settings.huggingface_api_key:
            raise AIConfigurationError(
                "AI verification is required, but HUGGINGFACE_API_KEY is not configured."
            )

        headers = {
            "Authorization": f"Bearer {settings.huggingface_api_key}",
            "Content-Type": "application/json",
        }
        messages = [
            {"role": "system", "content": "You are a careful evidence reviewer."},
            {"role": "user", "content": build_prompt(claim, evidence, score)},
        ]

        failures: list[str] = []
        async with httpx.AsyncClient(timeout=settings.huggingface_timeout) as client:
            live = await catalog(client, headers)
            attempts = plan_attempts(live)

            # A model that worked recently is overwhelmingly likely to work again.
            if _last_good_model and _last_good_model in attempts:
                attempts.remove(_last_good_model)
                attempts.insert(0, _last_good_model)

            if not attempts:
                raise AIUnavailableError(
                    "No Hugging Face model could be selected. The router returned an empty "
                    "catalogue for this token. Run `python scripts/check_ai.py` to diagnose."
                )

            for model_id in attempts:
                try:
                    note = await chat_once(client, headers, model_id, messages)
                except _TryNextModel as skipped:
                    failures.append(f"{model_id} ({skipped})")
                    continue
                _last_good_model = model_id
                return {
                    "available": True,
                    "required": True,
                    "degraded": False,
                    "provider": self.name,
                    "model": model_id,
                    "note": note[:1600],
                    "attempts": len(failures) + 1,
                }

        # Every candidate failed. Surface what was tried so the cause is obvious.
        _last_good_model = None
        raise AIUnavailableError(
            f"Required Hugging Face verification failed after trying {len(failures)} "
            f"model/provider combinations: {'; '.join(failures[:5])}. "
            "Run `python scripts/check_ai.py` locally with the same token to see which models are live."
        )
