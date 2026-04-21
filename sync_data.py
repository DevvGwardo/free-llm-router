#!/usr/bin/env python3
"""Sync latest provider data from awesome-free-llm-apis."""

import json
import urllib.request
from pathlib import Path

DATA_URL = "https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/main/data.json"
DATA_PATH = Path(__file__).parent / "data.json"


def sync():
    print(f"Fetching {DATA_URL}...")
    with urllib.request.urlopen(DATA_URL) as resp:
        data = json.loads(resp.read())
    
    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)
    
    providers = data.get("providers", [])
    total_models = sum(len(p.get("models", [])) for p in providers)
    print(f"Synced {len(providers)} providers, {total_models} models → {DATA_PATH}")
    
    for p in providers:
        models = [m["id"] for m in p.get("models", [])]
        print(f"  {p['name']}: {', '.join(models[:4])}{'...' if len(models) > 4 else ''}")


if __name__ == "__main__":
    sync()
