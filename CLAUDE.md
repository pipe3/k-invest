# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Local development
streamlit run app.py

# Docker (standard)
docker-compose up --build

# Docker (Portainer/production)
docker-compose -f docker-compose.portainer.yml up --build
```

There are no tests. Linting is done with **ruff** (configured in `pyproject.toml`). A pre-commit hook in `.claude/settings.json` runs `ruff check .` automatically before every `git commit`.

## Architecture

K-Invest is a Streamlit app with three independent AI analysis flows, all powered by the Anthropic Claude API via an agentic tool-use loop.

**The core pattern** (used identically in all three agents): call `client.messages.create()` in a `while True` loop, append tool results as user messages, and break when `stop_reason != "tool_use"`. Token counts are accumulated across all iterations.

### The four agents

| Module | Entry point | What it does |
|---|---|---|
| `agent.py` | `analyze_portfolio()` | Swing-trade analysis for depot + watchlist |
| `podcast_agent.py` | `analyze_latest_podcast()` | Analyzes "Doppelgänger Tech Talk" YouTube transcripts, extracts a structured watchlist via forced tool call (`save_doppelgaenger_watchlist`) |
| `discovery_agent.py` | `discover_stocks()` | Discovers new stock picks by sector, returns structured `[TICKERS_JSON]...[/TICKERS_JSON]` block parsed with regex |
| `screener_agent.py` | `analyze_screener_signals()` | Optional LLM fundamental check on top of screener signals; uses forced tool call `save_signal_verdicts` to emit structured verdicts (`bestätigt` / `vorsicht` / `abgelehnt`) per ticker |

The first three agents share the same two tools defined in `tools.py`:
- `get_stock_price_and_momentum` — yfinance wrapper, returns 1-month price history + metadata
- `search_recent_news` — routes to DuckDuckGo, Google Custom Search, or Tavily depending on `search_config["engine"]`

`screener_agent.py` uses the same two tools plus its own `save_signal_verdicts` tool (defined inline).

### Screener (non-LLM)

`screener.py` is a pure technical screener — no AI involved. It implements an **EMA-20 pullback strategy**:
- Fetches index constituents from Wikipedia (Nasdaq 100, S&P 500, Stoxx Europe 600) and caches them for 24 h in `index_cache.json` (`INDEX_CACHE_FILE` env var).
- Filters: price above SMA 50 and SMA 200, close within 0.5 % of EMA 20, average volume ≥ 500k, pullback pattern detected, stabilization candle present, CRV ≥ configured minimum.
- Converts Stoxx 600 prices to EUR natively; USD indices use the live EUR/USD rate from yfinance.
- Entry, stop-loss (10-day swing low), take-profit (recent 20-day high), position size, and max loss are all calculated in EUR.

### Background job pattern

All analyses run in `threading.Thread` to avoid blocking Streamlit. Job state is persisted to JSON files so the UI can poll status across reruns. Job files contain `{"status": "running"|"done"|"error", "result": {...}}`.

| Job file | Env var | Purpose |
|---|---|---|
| `depot_job.json` | `DEPOT_JOB_FILE` | Portfolio / watchlist analysis |
| `podcast_job.json` | `PODCAST_JOB_FILE` | Podcast analysis |
| `discovery_job.json` | `DISCOVERY_JOB_FILE` | Stock discovery |
| `screener_job.json` | `SCREENER_JOB_FILE` | Technical screener scan |
| `screener_llm_job.json` | `SCREENER_LLM_JOB_FILE` | Optional LLM fundamental check on screener signals |

Screener results are persisted separately in `screener_history.json` (`SCREENER_HISTORY_FILE`).

### Data persistence

All state is stored in JSON files. In Docker, `/data/` is mounted as a volume. File paths are set via environment variables (see `docker-compose.yml`) so nothing is hardcoded. The `settings.json` file stores API keys entered via the UI (as fallback when env vars are absent).

### Search engine configuration

`search_config` dict is assembled in `app.py` from `st.session_state` and passed down to all agents. Engine priority: if `engine == "google"` and keys present → Google; elif `engine == "tavily"` and key present → Tavily; else → DuckDuckGo (no key needed).

### Podcast-specific details

`podcast_tools.py` hardcodes the Doppelgänger channel ID (`UCZsFRBZ-5wNeFEqLFqnemcw`). The podcast agent uses `tool_choice={"type": "tool", "name": "save_doppelgaenger_watchlist"}` to force structured output on the first call, then makes a second unconstrained call to generate the markdown analysis text if the first response contained no text block.

## Environment Variables

All API keys can be provided via env vars **or** entered in the Streamlit sidebar (stored in `settings.json`). Env vars take precedence when `session_state` is empty.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Required for all analysis |
| `YOUTUBE_API_KEY` | Required for podcast tab |
| `GOOGLE_SEARCH_API_KEY` + `GOOGLE_CX_ID` | Optional: Google Custom Search |
| `TAVILY_API_KEY` | Optional: Tavily search |
| `INDEX_CACHE_FILE` | Path for screener index cache (default: `index_cache.json`) |
| `SCREENER_JOB_FILE` | Path for screener job state (default: `screener_job.json`) |
| `SCREENER_LLM_JOB_FILE` | Path for screener LLM job state (default: `screener_llm_job.json`) |
| `SCREENER_HISTORY_FILE` | Path for screener history (default: `screener_history.json`) |

## Cost Tracking

Pricing constants are defined in `app.py`:
- `CLAUDE_INPUT_PRICE_PER_M = 3.00` USD per million tokens
- `CLAUDE_OUTPUT_PRICE_PER_M = 15.00` USD per million tokens

These are displayed per analysis run and accumulated in `history.json`.
