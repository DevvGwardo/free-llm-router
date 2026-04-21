<div align="center">
  <br>
  <img src="https://raw.githubusercontent.com/DevvGwardo/free-llm-router/main/assets/logo.png" alt="free-llm-router" width="400">
  <br>
  <br>

  <p><strong>Combine every free LLM API tier into one endpoint.</strong></p>
  <p>A rotator proxy that gives you 30K+ free requests per day.</p>

  <br>

  [![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white)](https://python.org)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
  [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

  <br>
  <br>
</div>

---

## How it works

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#6366f1', 'primaryTextColor':'#fff', 'primaryBorderColor':'#818cf8', 'lineColor':'#6366f1', 'secondaryColor':'#1e1b4b', 'tertiaryColor':'#312e81', 'background':'#0f0d1a', 'mainBkg':'#1e1b4b', 'nodeBorder':'#818cf8', 'clusterBkg':'#1e1b4b', 'clusterBorder':'#312e81', 'titleColor':'#e0e7ff'}}}%%
flowchart LR
    subgraph app[" "]
        A["🤖 Your App\nor Hermes Agent"]
    end

    subgraph router["free-llm-router proxy"]
        direction TB
        B{"🔀 Router\n/weighted/round-robin"}
        C["📊 Rate Limiter\nRPM · RPD tracking"]
        D["🔄 Backoff\n429 → rotate\n5xx → exponential"]
        B --- C
        B --- D
    end

    subgraph providers["Free Providers"]
        direction TB
        P1["⚡ Groq\n30 RPM · 14.4K RPD\nllama-3.3-70b"]
        P2["🔥 Cerebras\n30 RPM · 14.4K RPD\ngpt-oss-120b"]
        P3["🌬️ Mistral\n1B tok/mo\nMistral Large 3"]
        P4["💎 Gemini\n10 RPM · 250 RPD\nGemini 2.5 Flash"]
        P5["🇨🇳 Z AI\nUnlimited\nGLM-4.7-Flash"]
        P6["☁️ Cloudflare\n50+ models\n10K neurons/day"]
    end

    A -->|"POST /v1/chat/completions"| B
    B -->|"pick best"| P1
    B -->|"pick best"| P2
    B -->|"pick best"| P3
    B -->|"pick best"| P4
    B -->|"pick best"| P5
    B -->|"pick best"| P6

    classDef app fill:#6366f1,stroke:#818cf8,color:#fff,stroke-width:2px
    classDef router fill:#7c3aed,stroke:#a78bfa,color:#fff,stroke-width:2px
    classDef limiter fill:#4f46e5,stroke:#818cf8,color:#fff,stroke-width:1px
    classDef provider fill:#059669,stroke:#34d399,color:#fff,stroke-width:1px

    class A app
    class B router
    class C,D limiter
    class P1,P2,P3,P4,P5,P6 provider
```

**One endpoint. OpenAI-compatible. Automatic rotation.**

---

## Free budget

| Provider | RPM | Requests/day | Speed | Models |
|----------|-----|-------------|-------|--------|
| ⚡ **Groq** | 30 | 14,400 | ~2,600 tok/s | llama-3.3-70b, qwen3-32b, deepseek-r1 |
| 🔥 **Cerebras** | 30 | 14,400 | ~2,600 tok/s | gpt-oss-120b, qwen-3-235b, llama3.1-8b |
| 🌬️ **Mistral** | ~1 RPS | ~1B tokens/mo | normal | Mistral Large 3, Codestral, Pixtral |
| 💎 **Gemini** | 10–15 | 250–1,000 | fast | Gemini 2.5 Flash, Flash-Lite |
| 🇨🇳 **Z AI** | 1 concurrent | unlimited | normal | GLM-4.7-Flash, GLM-4.5-Flash |
| ☁️ **Cloudflare** | shared | 10K neurons | normal | 50+ models (Llama, Mistral, Qwen, DeepSeek) |
| 🐙 **GitHub Models** | 10–15 | 50–150 | normal | GPT-4.1, o4-mini, DeepSeek-R1 |

**Combined: ~30,000+ requests/day for $0.**

No credit cards. No trials. Permanent free tiers.

---

## Quick start

```bash
# clone
git clone https://github.com/DevvGwardo/free-llm-router.git
cd free-llm-router

# install
pip install -r requirements.txt

# configure — just set your API keys
export GROQ_API_KEY="gsk_..."
# export CEREBRAS_API_KEY="..."    # add more = more free budget
# export MISTRAL_API_KEY="..."

# run
python run.py
```

**Test it:**

```bash
curl -X POST http://localhost:8686/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-70b-versatile",
    "messages": [{"role": "user", "content": "hello"}]
  }'
```

---

## Hermes integration

Point [Hermes Agent](https://github.com/NousResearch/hermes-agent) at the router:

```bash
hermes config set model.base_url http://localhost:8686/v1
hermes config set model.api_key not-needed
```

Hermes thinks it's talking to one endpoint.
The router secretly rotates across all your free providers.

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#6366f1', 'primaryTextColor':'#fff', 'lineColor':'#4f46e5', 'background':'#0f0d1a'}}}%%
flowchart LR
    H["🧬 Hermes Agent"] -->|"base_url: localhost:8686"| R["🔀 free-llm-router"]
    R -->|"auto-rotate"| G["⚡ Groq"]
    R -->|"auto-rotate"| C["🔥 Cerebras"]
    R -->|"auto-rotate"| M["🌬️ Mistral"]

    style H fill:#6366f1,stroke:#818cf8,color:#fff
    style R fill:#7c3aed,stroke:#a78bfa,color:#fff
    style G fill:#059669,stroke:#34d399,color:#fff
    style C fill:#059669,stroke:#34d399,color:#fff
    style M fill:#059669,stroke:#34d399,color:#fff
```

---

## Rotation strategies

Set in `config.yaml`:

```yaml
strategy: weighted  # default
```

| Strategy | Behavior | Best for |
|----------|----------|----------|
| **`weighted`** | Picks provider with most remaining capacity | Maximize throughput |
| **`round_robin`** | Cycles evenly through all providers | Even usage |
| **`fallback`** | Uses highest-priority provider until exhausted | Simplicity |

---

## Error handling

The router handles provider failures automatically:

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#6366f1', 'lineColor':'#4f46e5', 'background':'#0f0d1a'}}}%%
flowchart TD
    A["📨 Incoming Request"] --> B{"Route to\nbest provider"}
    B -->|"200 OK"| C["✅ Return response"]
    B -->|"429 Rate Limited"| D["⏳ Back off 60s\n→ rotate to next"]
    B -->|"5xx Server Error"| E["🔄 Exponential backoff\n30s → 60s → 120s → ..."]
    B -->|"401/403 Auth Error"| F["🚫 Disable 1hr\n→ rotate to next"]
    B -->|"Timeout"| G["⏭️ Rotate to next\nimmediately"]
    D --> H{"More providers\navailable?"}
    E --> H
    F --> H
    G --> H
    H -->|"yes"| B
    H -->|"no"| I["❌ 503 All exhausted"]

    style A fill:#6366f1,stroke:#818cf8,color:#fff
    style C fill:#059669,stroke:#34d399,color:#fff
    style I fill:#dc2626,stroke:#f87171,color:#fff
    style D fill:#d97706,stroke:#fbbf24,color:#fff
    style E fill:#d97706,stroke:#fbbf24,color:#fff
    style F fill:#dc2626,stroke:#f87171,color:#fff
    style G fill:#d97706,stroke:#fbbf24,color:#fff
```

---

## Status dashboard

```bash
curl http://localhost:8686/status | jq
```

```json
{
  "strategy": "weighted",
  "total_available": 2,
  "total_providers": 2,
  "providers": [
    {
      "name": "groq",
      "quota": {
        "rpm_remaining": 29,
        "rpd_remaining": 14399,
        "score": 0.983,
        "is_available": true
      }
    }
  ]
}
```

---

## Configuration

```yaml
# config.yaml

strategy: weighted       # round_robin | weighted | fallback
max_retries: 3           # attempts before giving up
# data_path: data.json   # optional: auto-detect models from awesome-free-llm-apis

providers:
  groq:
    enabled: true
    base_url: https://api.groq.com/openai/v1
    api_key: ${GROQ_API_KEY}

  cerebras:
    enabled: true
    base_url: https://api.cerebras.ai/v1
    api_key: ${CEREBRAS_API_KEY}

  mistral:
    enabled: true
    base_url: https://api.mistral.ai/v1
    api_key: ${MISTRAL_API_KEY}
```

**Every provider supports `${ENV_VAR}` syntax** — no keys in config files.

---

## API

The proxy exposes an OpenAI-compatible interface:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat completions (streaming supported) |
| `/v1/models` | GET | List all available models |
| `/status` | GET | Provider usage & quota dashboard |
| `/health` | GET | Health check |

---

## Get free API keys

All of these are **free, no credit card required**:

| Provider | Sign up | Time |
|----------|---------|------|
| ⚡ Groq | [console.groq.com](https://console.groq.com/keys) | Instant |
| 🔥 Cerebras | [cloud.cerebras.ai](https://cloud.cerebras.ai/) | Instant |
| 🌬️ Mistral | [console.mistral.ai](https://console.mistral.ai/api-keys) | Instant |
| 💎 Gemini | [aistudio.google.com](https://aistudio.google.com/app/apikey) | Instant |
| ☁️ Cloudflare | [dash.cloudflare.com](https://dash.cloudflare.com/profile/api-tokens) | Instant |

---

## Project structure

```
free-llm-router/
├── free_llm_router/
│   ├── router.py          # FastAPI app — the proxy
│   ├── providers.py       # Provider abstraction & API adaptation
│   ├── rate_limiter.py    # Per-provider RPM/RPD tracking
│   └── config.py          # Config loading & env var resolution
├── config.yaml            # Provider configuration
├── run.py                 # Entry point
├── sync_data.py           # Pull latest model data
└── requirements.txt
```

---

## Data source

Model data synced from [awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis) — the definitive list of permanent free LLM API tiers.

```bash
python sync_data.py  # pulls latest data.json
```

---

<div align="center">
  <p>Built with 🏴‍☠️ by <a href="https://github.com/DevvGwardo">DevvGwardo</a></p>
  <p>
    <a href="https://github.com/mnfst/awesome-free-llm-apis">awesome-free-llm-apis</a> ·
    <a href="https://github.com/NousResearch/hermes-agent">Hermes Agent</a>
  </p>
</div>
