# portfolio-risk-manager

A **CoinMarketCap Strategy Skill** for the BNB HACK: AI Trading Agent Edition — **Track 2 (Strategy Skills,
powered by CMC)**.

> Most strategies don't die from bad entries — they die from position sizing and drawdowns. This skill is the
> **risk layer**: it turns live CMC market data into a backtestable, portfolio-level risk management spec that
> decides *how much* to hold, *of what*, and *when to de-risk*. It is strategy-agnostic and can wrap any entry
> signal or asset basket.

## Why this is different

The track's example builds (momentum, sentiment-divergence, regime-detection) are all **entry/exit signal
generators**. This skill is the missing complement: the **portfolio risk overlay** that sits on top of any of
them. Its deliverable is a single, self-contained spec — and a backtester that proves the spec works.

## What it produces

A `portfolio_risk_spec.json` (validated by `schema/portfolio_risk_spec.schema.json`) covering:

- **Regime exposure budgeting** — Fear & Greed + derivatives funding + market trend → `risk_on / neutral /
  risk_off / crisis`, each mapped to a max gross exposure.
- **Volatility-targeted, inverse-vol sizing** — split the budget so the portfolio aims at a chosen vol.
- **Concentration limits** — per-asset weight caps and correlation-cluster down-weighting (hidden
  concentration).
- **Drawdown control** — a throttle ladder, a kill-switch to cash, and cooldown re-entry.
- **Event de-risking** — cut exposure around high-impact catalysts.
- **Idiosyncratic flags** — exclude whale-concentrated or illiquid tokens.

## Proof it's backtestable

```bash
cd backtest
python backtest.py --spec ../examples/sample_risk_spec.json   # single canonical path
python backtest.py --mc 200                                   # Monte Carlo robustness
```

Single canonical path (synthetic bull → crash → recovery, equal-weight buy & hold vs. the overlay):

| Metric         | Buy & Hold (EW) | Risk Overlay |
|----------------|-----------------|--------------|
| Total return   | 37.9%           | 35.5%        |
| Annualized vol | 64.7%           | 19.9%        |
| Sharpe         | 0.66            | **1.13**     |
| Max drawdown   | 69.2%           | **12.3%**    |
| Calmar         | 0.35            | **1.85**     |

**Monte Carlo (200 randomized paths)** — proof the Sharpe gain is robust, not one lucky path:

| Metric (mean)  | Buy & Hold (EW) | Risk Overlay |
|----------------|-----------------|--------------|
| Sharpe         | 0.84            | **1.30**     |
| Max drawdown   | 72.9%           | **15.6%**    |
| Calmar         | 1.18            | **1.88**     |

The overlay beats buy-and-hold on Sharpe in **66% of paths** (mean uplift **+0.46**) and cuts mean drawdown
~57 points — nearly matching the upside while taking a fraction of the risk. Pure-stdlib Python, no install.

## Layout

```
portfolio-risk-manager/
  SKILL.md                       # the skill (frontmatter + workflow) — CMC skill format
  schema/
    portfolio_risk_spec.schema.json   # JSON Schema for the deliverable
  examples/
    sample_risk_spec.json        # complete, valid example spec
  references/
    regime-detection.md          # trend-led regime rules
    exposure-and-limits.md       # trend filter, sizing, correlation, caps, smoothing
    drawdown-control.md          # throttle, kill-switch, re-entry
    spec-format.md               # field-by-field spec reference
    cmc-data-map.md              # which CMC MCP tool feeds which field
    data-access.md               # MCP / x402 / CLI routes into the Agent Hub
  backtest/
    backtest.py                  # pure-stdlib backtester (+ Monte Carlo)
    README.md                    # how to run + CSV format
    data/prices_sample.csv       # generated synthetic dataset (deterministic)
  ml/                            # OPTIONAL ML layer (pure stdlib, no install)
    ml_regime.py                 # from-scratch Random Forest crash classifier
    vol_forecast.py              # ATR-based Ridge volatility forecaster (rotation)
    README.md                    # walk-forward method + honest results
```

## Optional ML layer

Two complementary models, both **pure stdlib** (no install), both validated **out-of-sample, leakage-free**:

- `ml/ml_regime.py` — a **from-scratch Random Forest** that predicts near-term crash probability and sets
  exposure, with **walk-forward + purge** validation and a distilled human-readable tree. On a hard
  multi-regime dataset it lifts OOS Sharpe vs the reactive rules.
- `ml/vol_forecast.py` — an **ATR-based Ridge regression** that forecasts forward realized volatility for
  rotation / sizing. It is the only forecaster with R² > 0 (trailing vol and EWMA go negative across regime
  shifts); its payoff is tighter vol control and lower drawdown.

ML is positioned as a *complement* to the robust rule-based default — see `ml/README.md`.

## Built on the CMC Agent Hub (MCP / x402 / CLI)

Nine MCP tools drive the spec; the same data is reachable via **x402** (keyless pay-per-request on Base) and
the **CLI / REST** API (also used to pull history for backtests). See `references/data-access.md`. This broad,
real use of the Agent Hub also targets the **"Best Use of Agent Hub"** bonus.

## Install as a skill

```bash
cp -r portfolio-risk-manager /path/to/your/skills/directory/
```

Then configure the CoinMarketCap MCP (see `SKILL.md` → Prerequisites). API key from
https://pro.coinmarketcap.com/login.

## Submitting (Track 2)

Track 2 has **no on-chain registration** — submit this skill folder and the strategy spec through DoraHacks.
(On-chain registration, the BNB AI Agent SDK, the eligible-token list, and the minimum-trades rule apply to
**Track 1, Autonomous Trading Agents**, not here.)

## License

MIT
