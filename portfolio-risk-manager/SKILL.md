---
name: portfolio-risk-manager
description: |
  Turns live CoinMarketCap market data into a backtestable, portfolio-level RISK MANAGEMENT spec.
  This is NOT an entry-signal generator. It is a risk overlay that decides HOW MUCH to hold, of WHAT,
  and WHEN to de-risk: gross exposure, per-asset weight caps, correlation caps, market-regime exposure
  scaling (Fear & Greed + derivatives positioning + market trend), volatility targeting, event de-risking,
  and drawdown throttle / kill-switch. Output is a single machine-readable `portfolio_risk_spec.json`
  that any backtester can consume (a reference Python backtester is included).
  Use when the user asks about position sizing, exposure, portfolio risk, how much to allocate, when to
  cut risk, drawdown protection, correlation/diversification limits, or wants to wrap an existing strategy
  with a risk layer.
  Trigger: "risk spec", "position sizing", "how much should I allocate", "portfolio risk", "exposure",
  "de-risk", "drawdown protection", "diversify", "risk overlay", "size my portfolio", "/portfolio-risk-manager"
license: MIT
compatibility: ">=1.0.0"
user-invocable: true
allowed-tools:
  - mcp__cmc-mcp__search_cryptos
  - mcp__cmc-mcp__get_crypto_quotes_latest
  - mcp__cmc-mcp__get_crypto_technical_analysis
  - mcp__cmc-mcp__get_crypto_metrics
  - mcp__cmc-mcp__get_global_metrics_latest
  - mcp__cmc-mcp__get_global_crypto_derivatives_metrics
  - mcp__cmc-mcp__get_crypto_marketcap_technical_analysis
  - mcp__cmc-mcp__get_upcoming_macro_events
  - mcp__cmc-mcp__trending_crypto_narratives
---

# Portfolio Risk Manager Skill

Convert live CoinMarketCap data into a **portfolio-level risk management spec** — a structured, backtestable
JSON document that defines how capital should be sized, capped, scaled by market regime, and protected from
drawdowns. This skill is **strategy-agnostic**: it does not pick entries. It decides *exposure and sizing*
so it can wrap any set of candidate assets or any existing entry strategy.

> **Deliverable for the CMC Strategy Skills track:** a backtestable strategy spec, not a live agent.
> This skill produces `portfolio_risk_spec.json`. The companion `backtest/backtest.py` proves the spec is
> backtestable and quantifies how the risk overlay changes return, volatility, Sharpe, and max drawdown.

## Prerequisites

Verify the CMC MCP tools are available. If tools fail or return connection errors, ask the user to set up
the MCP connection:

```json
{
  "mcpServers": {
    "cmc-mcp": {
      "url": "https://mcp.coinmarketcap.com/mcp",
      "headers": {
        "X-CMC-MCP-API-KEY": "your-api-key"
      }
    }
  }
}
```

Get your API key from https://pro.coinmarketcap.com/login

## Data access (MCP / x402 / CLI)

This skill runs on the **CoinMarketCap AI Agent Hub** and supports all three of its access routes: **MCP**
(default, declared in `allowed-tools`), **x402** (keyless pay-per-request, 0.01 USDC on Base), and the
**CLI / REST** API (also used to pull historical data for backtesting). All three return the same fields and
build the same spec — see `references/data-access.md`.

## Core Principle

Most strategies die from position sizing and drawdowns, not from bad entries. The job of this skill is to
take an asset universe (and optionally an entry signal) and answer four questions, in order:

1. **Regime** — is the market risk-on, neutral, risk-off, or in crisis? (sets the overall risk budget)
2. **Sizing** — how is the risk budget split across assets so the portfolio targets a chosen volatility?
3. **Limits** — what caps prevent concentration (per-asset) and hidden concentration (correlation)?
4. **Protection** — how does exposure shrink as drawdown grows, and when do we fully de-risk?

Always emit a complete, valid spec even when some data is missing — fall back to documented defaults and
record what was assumed in `assumptions`.

## Workflow

### Step 0: Resolve the universe

Ask the user for an asset universe if not provided. Resolve each symbol to its CMC ID with `search_cryptos`.
If the user has no universe, propose a sensible default and confirm. (For the included example we use the
BNB-ecosystem eligible basket: ETH, LINK, UNI, AAVE, CAKE, AVAX.)

### Step 1: Classify the market regime (trend-led)

Pull the market-wide signals and classify the regime. The classification is **trend-led**: trend sets the
base regime and sentiment/leverage extremes only *trim* it — this keeps the book invested in healthy
uptrends (where the Sharpe is) and de-risks when the trend breaks. See `references/regime-detection.md` for
the exact rules.

- `get_crypto_marketcap_technical_analysis` → total-market-cap position vs ~200d MA and RSI (**primary**:
  sets risk_on / neutral / risk_off / crisis).
- `get_global_crypto_derivatives_metrics` → **funding rate** + open-interest change (trims one notch when
  leverage is one-sided).
- `get_global_metrics_latest` → Fear & Greed (trims one notch at extreme euphoria), plus BTC/ETH dominance,
  altcoin-season index, ETF flows for context.

Each regime maps to a maximum gross exposure (the risk budget). Document the inputs you used in
`regime.inputs`.

### Step 2: Gather per-asset risk inputs

For the resolved universe, batch where possible:

- `get_crypto_quotes_latest` (comma-separated IDs) → price, 24h volume, % changes (used as a recent-return
  proxy and a liquidity floor).
- `get_crypto_technical_analysis` (per asset) → RSI, moving averages, ATR-style volatility, pivot levels.
- `get_crypto_metrics` (per asset) → whale concentration and holder distribution → **idiosyncratic risk
  flags** (over-concentrated tokens get capped or excluded).

### Step 3: Check event risk

- `get_upcoming_macro_events` → if a high-impact event (Fed decision, major unlock, regulatory deadline)
  falls inside the de-risk window, set `event_risk` so exposure is cut around it.

Optionally `trending_crypto_narratives` to understand which assets share a narrative — assets in the same
hot narrative tend to be correlated, which informs the correlation cap.

### Step 4: Assemble the spec

Produce a single `portfolio_risk_spec.json` following `schema/portfolio_risk_spec.schema.json`. Fill every
block:

- `regime` — classification, the inputs used, and `exposure_by_regime` (the risk budget per regime).
- `sizing` — weighting method (default `inverse_vol`), `target_portfolio_vol_annual`, lookbacks,
  `max_weight_per_asset`, and `trend_filter` (drop assets below their own moving average).
- `correlation` — lookback and `max_pairwise`, plus how clusters are down-weighted.
- `limits` — `max_gross_exposure`, `max_assets`, `leverage`.
- `drawdown_control` — the `throttle` ladder, `kill_switch_dd`, and `reentry` rules.
- `event_risk` — de-risk window and multiplier.
- `execution` — exposure smoothing (`smoothing_mode`, default cut-fast/re-risk-slow) to cut whipsaw.
- `idiosyncratic_flags` — whale-concentration and liquidity floors.
- `rebalance` — frequency and drift band.
- `assumptions` — anything you defaulted because data was missing.

See `references/spec-format.md` for a field-by-field explanation and `examples/sample_risk_spec.json` for a
complete, valid example.

### Step 5: Backtest (proves it works)

Tell the user they can validate the spec immediately:

```bash
cd portfolio-risk-manager/backtest
python backtest.py --spec ../examples/sample_risk_spec.json   # single canonical path
python backtest.py --mc 200                                   # Monte Carlo robustness (200 paths)
```

The backtester runs the risk overlay against a buy-and-hold equal-weight baseline and prints CAGR,
annualized volatility, Sharpe, max drawdown, Calmar, and time-in-market for both. On the canonical path the
overlay lifts Sharpe ~0.66 → ~1.13 and cuts max drawdown ~69% → ~12%; across 200 randomized Monte Carlo
paths it beats buy-and-hold on Sharpe ~2/3 of the time (mean Sharpe ~0.84 → ~1.30). Pure-stdlib Python, no
dependencies — see `backtest/README.md`.

## Optional: ML layer (regime classifier + volatility forecaster)

The trend-led regime rules are the robust default. Two **optional** machine-learning models (in `ml/`, pure
standard library — no install) can complement them, each validated out-of-sample with no leakage:

- **Crash classifier** (`ml/ml_regime.py`) — a from-scratch Random Forest predicting near-term crash
  probability from CMC features → sets exposure through the same risk machinery. Uses **walk-forward
  validation with a purge gap** (never random k-fold — that leaks the future on time series), reports feature
  importance, and distills a human-readable tree. Honest out-of-sample **Rules vs ML** backtest.
- **Volatility forecaster** (`ml/vol_forecast.py`) — an **ATR-based Ridge regression** predicting forward
  realized volatility per asset → feeds `sizing.target_portfolio_vol` scaling and inverse-vol rotation. It
  beats trailing-vol and EWMA baselines (which go R²-negative across regimes); its payoff is tighter vol
  control and lower drawdown.

Treat ML as a *complement* adopted only after walk-forward validation, not a replacement. See `ml/README.md`.

## How the risk mechanisms map to CMC data

| Risk mechanism            | CMC MCP source                                   | What it controls                          |
|---------------------------|--------------------------------------------------|-------------------------------------------|
| Regime budget (primary)   | `get_crypto_marketcap_technical_analysis` (trend)| Overall gross exposure ceiling            |
| Crowding / leverage trim  | `get_global_crypto_derivatives_metrics` (funding)| Trim a notch when funding/OI is extreme   |
| Sentiment trim            | `get_global_metrics_latest` (Fear & Greed)       | Trim a notch at extreme euphoria          |
| Asset trend filter        | `get_crypto_technical_analysis` (MA)             | Drop assets below their own moving average |
| Per-asset volatility      | `get_crypto_technical_analysis` (ATR/RSI)        | Inverse-vol sizing, target-vol scaling    |
| Liquidity floor           | `get_crypto_quotes_latest` (24h volume)          | Exclude illiquid names                    |
| Idiosyncratic concentration | `get_crypto_metrics` (whale %)                 | Cap/exclude whale-heavy tokens            |
| Event risk                | `get_upcoming_macro_events`                       | Cut exposure around catalysts             |
| Correlation clusters      | `trending_crypto_narratives` (+ price corr)      | Correlation cap / cluster down-weight     |

See `references/cmc-data-map.md` for the detailed mapping.

## Output format

Always present:

1. A short plain-language summary of the regime and the resulting risk posture (1–3 sentences).
2. The full `portfolio_risk_spec.json` in a fenced ```json block.
3. The exact backtest command to validate it.

Example summary line:
> *Regime: risk_on (total mcap above 200d MA, RSI 56, funding mildly positive, Fear & Greed 54 — no trims).
> Risk budget 100% gross, inverse-vol sized to a 40% vol target, assets below their 50d MA excluded,
> per-asset cap 25%, exposure cut-fast/re-risk-slow, kill-switch at -25% drawdown.*

## Important notes

- This is risk tooling, not financial advice.
- The spec is descriptive and deterministic: given the same inputs, the same spec — so results are reproducible.
- Never emit an incomplete spec. If a tool fails, fall back to defaults in `references/spec-format.md` and
  list the fallback in `assumptions`.
- Keep the spec self-contained: a backtester should need nothing but the spec and a price series.

## Handling tool failures

1. **search_cryptos fails**: cannot size an unknown asset. Ask the user to confirm symbols / contract addresses.
2. **get_crypto_marketcap_technical_analysis fails**: the trend-led regime loses its primary input — default
   the regime to `neutral` and lean on the funding/sentiment trims; record it in `assumptions`.
3. **get_global_crypto_derivatives_metrics fails**: skip the funding/leverage trim; note it.
4. **get_global_metrics_latest fails**: skip the euphoria trim and dominance/altseason context; note it.
5. **get_crypto_technical_analysis fails**: fall back to equal-weight sizing and disable the asset trend
   filter (`sizing.trend_filter.enabled=false`); note it.
6. **get_crypto_metrics fails**: skip whale-concentration flags; note it.
7. **get_upcoming_macro_events fails**: set `event_risk.enabled=false`; note it.

Always deliver a complete, valid spec with documented assumptions rather than no spec at all.
