"""
The rotator proxy — main FastAPI app.

Accepts OpenAI-compatible requests and routes them to the best
available free provider.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .config import load_config, load_providers
from .providers import (
    ProviderConfig,
    ProviderType,
    adapt_request_body,
    adapt_response,
    build_request_headers,
    build_request_url,
)
from .rate_limiter import ProviderQuota

logger = logging.getLogger("free-llm-router")

# global state
_providers: list[ProviderConfig] = []
_quotas: dict[str, ProviderQuota] = {}
_client: httpx.AsyncClient | None = None
_round_robin_index: int = 0
_config: dict = {}


def _init_quotas(providers: list[ProviderConfig]):
    """Initialize rate limiters for each provider."""
    global _quotas
    _quotas = {}
    for p in providers:
        _quotas[p.name] = ProviderQuota(
            rpm_limit=p.rpm_limit,
            rpd_limit=p.rpd_limit,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown."""
    global _providers, _client, _config

    _config = load_config()
    _providers = load_providers(_config)
    _init_quotas(_providers)

    _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))

    strategy = _config.get("strategy", "weighted")
    logger.info(f"free-llm-router started with {len(_providers)} providers, strategy={strategy}")
    for p in _providers:
        logger.info(f"  {p.name}: {p.models[:3]}{'...' if len(p.models) > 3 else ''} "
                    f"(RPM={p.rpm_limit}, RPD={p.rpd_limit})")

    yield

    if _client:
        await _client.aclose()


app = FastAPI(
    title="free-llm-router",
    description="Rotator proxy for free LLM API providers",
    lifespan=lifespan,
)


def _select_provider(model: Optional[str] = None) -> Optional[ProviderConfig]:
    """Select the best available provider based on strategy."""
    global _round_robin_index

    strategy = _config.get("strategy", "weighted")

    # filter to available providers that support the model
    candidates = []
    for p in _providers:
        if not p.enabled:
            continue
        quota = _quotas.get(p.name)
        if not quota or not quota.is_available:
            continue
        if model and model != "default" and p.models[0] != "default":
            if model not in p.models:
                continue
        candidates.append((p, quota))

    if not candidates:
        # fallback: try any provider that's not auth-blocked
        for p in _providers:
            quota = _quotas.get(p.name)
            if quota and time.time() > quota._exhausted_until:
                candidates.append((p, quota))

    if not candidates:
        return None

    if strategy == "round_robin":
        _round_robin_index = (_round_robin_index + 1) % len(candidates)
        return candidates[_round_robin_index][0]

    elif strategy == "weighted":
        # pick provider with highest remaining capacity score
        candidates.sort(key=lambda x: x[1].score, reverse=True)
        return candidates[0][0]

    elif strategy == "fallback":
        # use first available (priority order)
        candidates.sort(key=lambda x: x[0].priority, reverse=True)
        return candidates[0][0]

    # default: weighted
    candidates.sort(key=lambda x: x[1].score, reverse=True)
    return candidates[0][0]


async def _forward_request(
    provider: ProviderConfig,
    body: dict,
) -> tuple[dict, int]:
    """Forward a request to a provider. Returns (response_data, status_code)."""
    assert _client is not None

    model = body.get("model", provider.models[0])
    url = build_request_url(provider, model)
    headers = build_request_headers(provider)
    adapted_body = adapt_request_body(body, provider)

    # set the provider's model
    if provider.provider_type != ProviderType.GEMINI:
        adapted_body["model"] = model

    resp = await _client.post(url, json=adapted_body, headers=headers)

    try:
        resp_data = resp.json()
    except Exception:
        resp_data = {"error": resp.text}

    return resp_data, resp.status_code


async def _forward_streaming_request(
    provider: ProviderConfig,
    body: dict,
):
    """Forward a streaming request. Yields SSE chunks."""
    assert _client is not None

    model = body.get("model", provider.models[0])
    url = build_request_url(provider, model)
    headers = build_request_headers(provider)
    adapted_body = adapt_request_body(body, provider)

    if provider.provider_type != ProviderType.GEMINI:
        adapted_body["model"] = model
    adapted_body["stream"] = True

    async with _client.stream("POST", url, json=adapted_body, headers=headers) as resp:
        async for line in resp.aiter_lines():
            if line:
                yield f"{line}\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions endpoint."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    model = body.get("model", "")
    is_streaming = body.get("stream", False)
    max_retries = _config.get("max_retries", 3)

    tried_providers: set[str] = set()
    last_error = None

    for attempt in range(max_retries):
        provider = _select_provider(model)
        if not provider or provider.name in tried_providers:
            # try any remaining
            for p in _providers:
                if p.name not in tried_providers:
                    provider = p
                    break

        if not provider:
            raise HTTPException(
                503,
                detail=f"All providers exhausted. Tried: {tried_providers}. "
                       f"Last error: {last_error}"
            )

        tried_providers.add(provider.name)
        quota = _quotas[provider.name]

        try:
            if is_streaming:
                return await _handle_streaming(provider, body, quota)
            else:
                return await _handle_standard(provider, body, quota)

        except httpx.TimeoutException:
            quota.record_error(504)
            last_error = f"{provider.name}: timeout"
            logger.warning(f"Provider {provider.name} timed out, rotating")
            continue

        except Exception as e:
            last_error = f"{provider.name}: {e}"
            logger.warning(f"Provider {provider.name} failed: {e}, rotating")
            continue

    raise HTTPException(
        503,
        detail=f"All {max_retries} attempts failed. Providers tried: {tried_providers}"
    )


async def _handle_standard(
    provider: ProviderConfig,
    body: dict,
    quota: ProviderQuota,
) -> JSONResponse:
    """Handle a standard (non-streaming) request."""
    resp_data, status_code = await _forward_request(provider, body)

    if status_code >= 400:
        quota.record_error(status_code)
        error_msg = resp_data.get("error", resp_data.get("message", str(resp_data)))
        raise HTTPException(status_code, f"Provider {provider.name}: {error_msg}")

    quota.record_request()

    # adapt response back to OpenAI format
    original_model = body.get("model", "")
    adapted = adapt_response(resp_data, provider, original_model)

    # inject routing metadata
    adapted["_router"] = {
        "provider": provider.name,
        "attempt": len([p for p in _quotas.values() if not p.is_available]),
    }

    return JSONResponse(adapted)


async def _handle_streaming(
    provider: ProviderConfig,
    body: dict,
    quota: ProviderQuota,
) -> StreamingResponse:
    """Handle a streaming request."""
    # streaming is harder to adapt for non-OpenAI providers
    # for now, just forward SSE for OpenAI-compatible providers
    if provider.provider_type != ProviderType.OPENAI_COMPATIBLE:
        # fall back to non-streaming
        resp_data, status_code = await _forward_request(provider, body)
        if status_code >= 400:
            quota.record_error(status_code)
            raise HTTPException(status_code, f"Provider {provider.name} error")
        quota.record_request()
        original_model = body.get("model", "")
        adapted = adapt_response(resp_data, provider, original_model)
        return JSONResponse(adapted)

    # streaming forward for OpenAI-compatible
    quota.record_request()

    async def generate():
        try:
            async for chunk in _forward_streaming_request(provider, body):
                yield chunk
        except Exception as e:
            logger.error(f"Streaming error from {provider.name}: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Router-Provider": provider.name},
    )


@app.get("/v1/models")
async def list_models():
    """List all available models across providers (OpenAI format)."""
    models = []
    seen = set()
    for p in _providers:
        for m in p.models:
            if m not in seen and m != "default":
                seen.add(m)
                models.append({
                    "id": m,
                    "object": "model",
                    "owned_by": p.name,
                })
    return {"object": "list", "data": models}


@app.get("/status")
async def status():
    """Router status dashboard."""
    return {
        "strategy": _config.get("strategy", "weighted"),
        "providers": [
            {
                "name": p.name,
                "type": p.provider_type.value,
                "models": p.models,
                "enabled": p.enabled,
                "quota": _quotas.get(p.name, ProviderQuota()).to_dict(),
            }
            for p in _providers
        ],
        "total_available": sum(1 for q in _quotas.values() if q.is_available),
        "total_providers": len(_providers),
    }


@app.get("/health")
async def health():
    return {"status": "ok", "providers": len(_providers)}


# =============================================================================
# BUDDY ENDPOINT — fan out to two models in parallel, return both responses
# =============================================================================

def _build_body(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: Optional[int],
    system: Optional[str],
) -> dict:
    """Build a chat completions body for one model."""
    msgs = messages.copy()
    if system:
        msgs = [{"role": "system", "content": system}] + msgs
    body: dict = {
        "model": model,
        "messages": msgs,
        "temperature": temperature,
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    return body


async def _call_model(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: Optional[int],
    system: Optional[str],
) -> tuple[dict, int, float, Optional[ProviderConfig]]:
    """
    Resolve model to provider and forward the request.
    Returns (response_data, status_code, elapsed_ms, provider).
    """
    assert _client is not None

    body = _build_body(model, messages, temperature, max_tokens, system)
    provider = _select_provider(model)
    if not provider:
        return {"error": f"No provider available for model: {model}"}, 503, 0, None

    url = build_request_url(provider, model)
    headers = build_request_headers(provider)
    adapted_body = adapt_request_body(body, provider)
    if provider.provider_type != ProviderType.GEMINI:
        adapted_body["model"] = model

    t0 = time.monotonic()
    resp = await _client.post(url, json=adapted_body, headers=headers)
    elapsed_ms = (time.monotonic() - t0) * 1000

    try:
        resp_data = resp.json()
    except Exception:
        resp_data = {"error": resp.text}

    return resp_data, resp.status_code, elapsed_ms, provider


@app.post("/v1/buddy")
async def buddy_completions(request: Request):
    """
    Fan out to two models in parallel, return both responses.

    Request body:
        model_a          primary model (e.g. deepseek-ai/deepseek-v4-flash)
        model_b          buddy model (e.g. minimax/m2.5-free)
        messages         shared conversation context
        temperature_a    optional temp for model_a (default 0.7)
        temperature_b    optional temp for model_b (default 0.7)
        max_tokens_a     optional max_tokens for model_a
        max_tokens_b     optional max_tokens for model_b
        system_a         optional system prompt for model_a
        system_b         optional system prompt for model_b

    Response:
        model_a_response  raw chat completion from model_a
        model_b_response  raw chat completion from model_b
        model_a_ms        milliseconds model_a took
        model_b_ms        milliseconds model_b took
        model_a_provider  provider name for model_a
        model_b_provider  provider name for model_b
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    model_a = body.get("model_a")
    model_b = body.get("model_b")
    messages = body.get("messages", [])
    temp_a = body.get("temperature_a", 0.7)
    temp_b = body.get("temperature_b", 0.7)
    max_a = body.get("max_tokens_a")
    max_b = body.get("max_tokens_b")
    sys_a = body.get("system_a")
    sys_b = body.get("system_b")

    if not model_a or not model_b:
        raise HTTPException(400, "model_a and model_b are required")
    if not messages:
        raise HTTPException(400, "messages is required")

    # Fire both in parallel via asyncio.gather
    task_a = _call_model(model_a, messages, temp_a, max_a, sys_a)
    task_b = _call_model(model_b, messages, temp_b, max_b, sys_b)

    results = await asyncio.gather(task_a, task_b, return_exceptions=True)

    result: dict = {}

    for label, resp in [("a", results[0]), ("b", results[1])]:
        prefix = f"model_{label}"
        if isinstance(resp, Exception):
            result[f"{prefix}_response"] = {"error": str(resp)}
            result[f"{prefix}_ms"] = 0
            result[f"{prefix}_provider"] = None
            continue

        data, status, ms, provider = resp
        result[f"{prefix}_ms"] = round(ms, 1)
        result[f"{prefix}_provider"] = provider.name if provider else None

        if isinstance(resp, Exception) or status >= 400:
            err_data = resp if isinstance(resp, Exception) else data
            result[f"{prefix}_response"] = {
                "error": str(err_data) if isinstance(err_data, Exception) else err_data.get("error", str(err_data)),
                "_status": status if not isinstance(resp, Exception) else 0,
            }
        else:
            adapted = adapt_response(data, provider, body.get(f"model_{label}"))
            adapted["_router"] = {"provider": provider.name if provider else None}
            result[f"{prefix}_response"] = adapted

    return JSONResponse(result)
