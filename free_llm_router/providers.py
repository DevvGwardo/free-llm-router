"""
Provider abstraction.

Handles differences between OpenAI-compatible providers
and non-standard ones (Cloudflare, Gemini).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderType(Enum):
    OPENAI_COMPATIBLE = "openai"  # most providers
    CLOUDFLARE = "cloudflare"     # custom URL format
    GEMINI = "gemini"             # Google's API shape


@dataclass
class ProviderConfig:
    """A configured provider with API key."""
    name: str
    provider_type: ProviderType
    base_url: str
    api_key: str
    models: list[str]
    rpm_limit: int = 60
    rpd_limit: int = 10000
    enabled: bool = True
    priority: int = 0  # higher = preferred


def detect_provider_type(name: str, base_url: str) -> ProviderType:
    """Auto-detect provider type from name/url."""
    name_lower = name.lower()
    url_lower = base_url.lower()
    
    if "cloudflare" in name_lower or "cloudflare" in url_lower:
        return ProviderType.CLOUDFLARE
    if "googleapis" in url_lower or "gemini" in name_lower:
        return ProviderType.GEMINI
    return ProviderType.OPENAI_COMPATIBLE


def parse_rate_limit(rate_str: str) -> tuple[int, int]:
    """Parse rate limit string like '30 RPM, 14,400 RPD' into (rpm, rpd)."""
    rpm = 60
    rpd = 10000
    
    if not rate_str:
        return rpm, rpd
    
    import re
    
    # extract RPM
    rpm_match = re.search(r'(\d+)\s*RPM', rate_str, re.IGNORECASE)
    if rpm_match:
        rpm = int(rpm_match.group(1))
    
    # extract RPD (handle commas)
    rpd_match = re.search(r'([\d,]+)\s*RPD', rate_str, re.IGNORECASE)
    if rpd_match:
        rpd = int(rpd_match.group(1).replace(',', ''))
    
    return rpm, rpd


def build_request_headers(provider: ProviderConfig) -> dict[str, str]:
    """Build HTTP headers for a provider."""
    headers = {
        "Content-Type": "application/json",
    }
    
    if provider.provider_type == ProviderType.OPENAI_COMPATIBLE:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    elif provider.provider_type == ProviderType.GEMINI:
        # Gemini uses query param, not header
        pass
    elif provider.provider_type == ProviderType.CLOUDFLARE:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    
    return headers


def build_request_url(provider: ProviderConfig, model: str) -> str:
    """Build the full request URL for a provider."""
    if provider.provider_type == ProviderType.OPENAI_COMPATIBLE:
        # standard OpenAI format
        base = provider.base_url.rstrip('/')
        return f"{base}/chat/completions"
    
    elif provider.provider_type == ProviderType.GEMINI:
        # Gemini: /models/{model}:generateContent?key={key}
        base = provider.base_url.rstrip('/')
        return f"{base}/models/{model}:generateContent?key={provider.api_key}"
    
    elif provider.provider_type == ProviderType.CLOUDFLARE:
        # Cloudflare: /ai/run/{model}
        base = provider.base_url.rstrip('/')
        if '{account_id}' in base:
            raise ValueError("Cloudflare requires account_id in base_url. "
                           "Set it to: https://api.cloudflare.com/client/v4/accounts/YOUR_ID/ai/run")
        return f"{base}/{model}"
    
    return f"{provider.base_url.rstrip('/')}/chat/completions"


def adapt_request_body(body: dict, provider: ProviderConfig) -> dict:
    """Adapt the request body for a provider's expected format."""
    if provider.provider_type == ProviderType.GEMINI:
        return _openai_to_gemini(body)
    elif provider.provider_type == ProviderType.CLOUDFLARE:
        return _openai_to_cloudflare(body)
    # OpenAI-compatible: pass through
    return body


def adapt_response(resp_data: dict, provider: ProviderConfig, original_model: str) -> dict:
    """Adapt the response back to OpenAI format."""
    if provider.provider_type == ProviderType.GEMINI:
        return _gemini_to_openai(resp_data, original_model)
    elif provider.provider_type == ProviderType.CLOUDFLARE:
        return _cloudflare_to_openai(resp_data, original_model)
    return resp_data


def _openai_to_gemini(body: dict) -> dict:
    """Convert OpenAI request to Gemini format."""
    contents = []
    system_instruction = None
    
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "system":
            system_instruction = {"parts": [{"text": content}]}
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})
        else:
            contents.append({"role": "user", "parts": [{"text": content}]})
    
    gemini_body: dict = {"contents": contents}
    
    if system_instruction:
        gemini_body["systemInstruction"] = system_instruction
    
    # map generation params
    gen_config = {}
    if "max_tokens" in body:
        gen_config["maxOutputTokens"] = body["max_tokens"]
    if "temperature" in body:
        gen_config["temperature"] = body["temperature"]
    if "top_p" in body:
        gen_config["topP"] = body["top_p"]
    if gen_config:
        gemini_body["generationConfig"] = gen_config
    
    return gemini_body


def _gemini_to_openai(data: dict, model: str) -> dict:
    """Convert Gemini response to OpenAI format."""
    content = ""
    candidates = data.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        content = "".join(p.get("text", "") for p in parts)
    
    usage = data.get("usageMetadata", {})
    
    return {
        "id": f"chatcmpl-free-{model}",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "completion_tokens": usage.get("candidatesTokenCount", 0),
            "total_tokens": usage.get("totalTokenCount", 0),
        },
    }


def _openai_to_cloudflare(body: dict) -> dict:
    """Convert OpenAI request to Cloudflare Workers AI format."""
    messages = body.get("messages", [])
    cf_body: dict = {"messages": messages}
    
    if "max_tokens" in body:
        cf_body["max_tokens"] = body["max_tokens"]
    if "temperature" in body:
        cf_body["temperature"] = body["temperature"]
    if "stream" in body:
        cf_body["stream"] = body["stream"]
    
    return cf_body


def _cloudflare_to_openai(data: dict, model: str) -> dict:
    """Convert Cloudflare response to OpenAI format."""
    result = data.get("result", {})
    content = result.get("response", "")
    
    return {
        "id": f"chatcmpl-free-{model}",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
