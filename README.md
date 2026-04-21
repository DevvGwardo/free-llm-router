# free-llm-router

A rotator proxy for free LLM API providers. Accepts OpenAI-compatible requests and routes them across multiple free-tier providers with automatic rate limit tracking and rotation.

## What it does

You have free API keys from Groq, Cerebras, Mistral, Gemini, etc. Each has rate limits. This proxy sits between your app and the APIs, and rotates between providers so you get the combined rate limit of all of them.

**Combined free budget (approximate):**
- Groq: 14,400 req/day @ 30 RPM
- Cerebras: 14,400 req/day @ 30 RPM
- Mistral: ~1B tokens/month
- Gemini: 250-1000 req/day
- + more if you add keys

That's **30K+ requests/day** for free.

## Setup

```bash
# install deps
pip install -r requirements.txt

# copy config template
cp config.yaml config.yaml.local

# set your API keys
export GROQ_API_KEY="gsk_..."
export CEREBRAS_API_KEY="csk-..."
export MISTRAL_API_KEY="..."

# run
python run.py --config config.yaml.local
```

## Hermes integration

Point hermes at the proxy:

```bash
# configure hermes to use the rotator
hermes config set model.base_url http://localhost:8686/v1
hermes config set model.api_key not-needed
hermes config set model.provider free-router

# or edit config.yaml directly:
# model:
#   base_url: http://localhost:8686/v1
#   api_key: not-needed
```

Then start the proxy before using hermes:

```bash
# terminal 1: run the router
python run.py

# terminal 2: use hermes normally
hermes
```

Hermes thinks it's talking to one endpoint, but the router rotates across all your free providers.

## Rotation strategies

Set in `config.yaml`:

| Strategy | Behavior |
|----------|----------|
| `weighted` (default) | Picks provider with most remaining capacity |
| `round_robin` | Cycles evenly through all available providers |
| `fallback` | Uses highest-priority provider until exhausted |

## Status endpoint

```bash
curl http://localhost:8686/status | python -m json.tool
```

Shows per-provider usage, remaining capacity, and error state.

## How it works

1. Receives OpenAI-format request
2. Scores available providers (capacity remaining, errors, rate limits)
3. Forwards to best provider with auth headers adapted
4. On 429/5xx: marks provider backlogged, rotates to next
5. On success: records usage, returns response

Non-OpenAI providers (Gemini, Cloudflare) are auto-adapted to/from OpenAI format.

## Config reference

```yaml
strategy: weighted       # round_robin | weighted | fallback
max_retries: 3           # attempts before giving up
data_path: /path/to/data.json  # optional: auto-detect models/rates

providers:
  groq:
    enabled: true
    base_url: https://api.groq.com/openai/v1
    api_key: ${GROQ_API_KEY}    # env var or literal
    priority: 0                  # higher = preferred (fallback strategy)
    # models: [...]             # auto-detected from data.json if set
    # rpm_limit: 30             # override if not using data.json
    # rpd_limit: 14400
```

## Syncing provider data

Optionally pull model data from [awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis):

```bash
curl -o data.json https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/main/data.json
```

Then set `data_path: data.json` in config. Models and rate limits auto-populate.
