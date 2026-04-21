"""
Configuration loading.

Loads provider config from YAML and optionally syncs model data
from the awesome-free-llm-apis data.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from typing import Optional

import yaml

from .providers import ProviderConfig, ProviderType, detect_provider_type, parse_rate_limit

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config(path: Optional[str] = None) -> dict:
    """Load config.yaml."""
    if path is None:
        path = os.getenv("FREEROUTER_CONFIG")
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def load_providers(config: dict | None = None) -> list[ProviderConfig]:
    """Load provider configs, resolving env vars for API keys."""
    if config is None:
        config = load_config()
    
    providers = []
    data_path = config.get("data_path")
    provider_configs = config.get("providers", {})
    
    # optionally merge with awesome-free-llm-apis data.json
    model_data = {}
    if data_path and Path(data_path).exists():
        with open(data_path) as f:
            raw = json.load(f)
            for p in raw.get("providers", []):
                key = p["name"].lower().replace(" ", "_").replace("(", "").replace(")", "")
                model_data[key] = p
    
    for name, pcfg in provider_configs.items():
        if not pcfg.get("enabled", True):
            continue
        
        # resolve API key from env
        api_key = pcfg.get("api_key", "")
        if api_key.startswith("${") and api_key.endswith("}"):
            env_var = api_key[2:-1]
            api_key = os.getenv(env_var, "")
        
        if not api_key:
            continue  # skip providers without keys
        
        base_url = pcfg.get("base_url", "")
        provider_type = detect_provider_type(name, base_url)
        
        # get models from config or data.json
        models = pcfg.get("models", [])
        if not models:
            # try to pull from data.json
            for dk, dv in model_data.items():
                if name.lower() in dk or dk in name.lower():
                    models = [m["id"] for m in dv.get("models", [])
                             if m.get("modality", "").lower().startswith("text")]
                    break
        
        if not models:
            models = ["default"]
        
        # get rate limits
        rpm = pcfg.get("rpm_limit", 60)
        rpd = pcfg.get("rpd_limit", 10000)
        
        # try to get from data.json
        for dk, dv in model_data.items():
            if name.lower() in dk or dk in name.lower():
                # use first model's rate limit as proxy
                first_model = dv.get("models", [{}])[0]
                if first_model.get("rateLimit"):
                    rpm_parsed, rpd_parsed = parse_rate_limit(first_model["rateLimit"])
                    if not pcfg.get("rpm_limit"):
                        rpm = rpm_parsed
                    if not pcfg.get("rpd_limit"):
                        rpd = rpd_parsed
                break
        
        providers.append(ProviderConfig(
            name=name,
            provider_type=provider_type,
            base_url=base_url,
            api_key=api_key,
            models=models,
            rpm_limit=rpm,
            rpd_limit=rpd,
            priority=pcfg.get("priority", 0),
        ))
    
    return providers
