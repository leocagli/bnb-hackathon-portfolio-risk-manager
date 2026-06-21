# Regime Detection (trend-led)

The regime sets the **risk budget** — the maximum gross exposure the portfolio is allowed to run. It is the
single most important risk decision.

The design is **trend-led**: trend is the primary axis, and sentiment / leverage extremes only *trim*
exposure. This is deliberate. A purely contrarian rule (fade greed, fade high funding) exits healthy
uptrends too early and leaves most of the return — and most of the Sharpe — on the table. Letting the trend
lead keeps the portfolio invested while the market is rising and pulls it to safety only when the trend
actually breaks, which is when crashes happen. In Monte Carlo this is what lifts risk-adjusted return
(mean Sharpe ~0.84 → ~1.30) instead of merely cutting drawdown.

## Inputs (from CMC MCP)

| Signal              | Tool                                          | Field used                          |
|---------------------|-----------------------------------------------|-------------------------------------|
| Trend (primary)     | `get_crypto_marketcap_technical_analysis`      | total mcap vs ~200d MA + RSI        |
| Crowding / leverage | `get_global_crypto_derivatives_metrics`        | funding rate (8h) + open-interest change |
| Sentiment           | `get_global_metrics_latest`                    | Fear & Greed index (0–100)          |

## Step 1 — Trend sets the base regime

Let `ratio = market_index / MA(market_index, ~200d)` and `r = RSI(market_index, 14)`.

| Condition                         | Base regime | Meaning                              |
|-----------------------------------|-------------|--------------------------------------|
| `ratio ≥ 1.00` and `RSI < 75`     | risk_on     | Confirmed, non-extended uptrend      |
| `ratio ≥ 1.00` and `RSI ≥ 75`     | neutral     | Uptrend but blow-off — trim          |
| `0.90 ≤ ratio < 1.00`             | risk_off    | Mild downtrend                       |
| `ratio < 0.90`                    | crisis      | Deep downtrend — protect capital     |

## Step 2 — Trims (can only reduce exposure, never raise it)

Apply each that is true; each steps the regime down one notch
(`risk_on → neutral → risk_off → crisis`):

| Trim trigger                                  | Why                                              |
|-----------------------------------------------|--------------------------------------------------|
| Funding (8h) > 0.05% **and** OI change > 20%  | One-sided leverage building → squeeze/liquidation risk |
| Fear & Greed ≥ 90                             | Extreme euphoria → reflexive drawdowns start here |

Trims never step *up*: good sentiment in a downtrend does not re-risk the book. Re-engagement happens only
when price reclaims the trend (Step 1) and, at the asset level, via the trend filter in
`exposure-and-limits.md`.

## Step 3 — Map regime → exposure budget

| Regime    | Default max gross exposure |
|-----------|----------------------------|
| risk_on   | 1.00                       |
| neutral   | 0.65                       |
| risk_off  | 0.30                       |
| crisis    | 0.00 (full de-risk to cash)|

These are `regime.exposure_by_regime` in the spec. Tune the budgets to risk appetite; the labels and rules
stay the same so the decision is always auditable. The final gross is this budget combined with
volatility targeting, the drawdown throttle, and event de-risking (see `exposure-and-limits.md` and
`drawdown-control.md`).

## Worked examples

- **Healthy bull:** ratio 1.18, RSI 63, funding 0.02%, F&G 68 → base `risk_on`, no trims → **risk_on (1.0)**.
  The book stays fully deployed (subject to vol targeting) and captures the trend.
- **Blow-off top:** ratio 1.30, RSI 82, funding 0.06% with OI +25%, F&G 92 → base `neutral`, two trims →
  **crisis (0.0)**. Leverage + euphoria on an over-extended tape pulls the book to cash before the reversal.
- **Crash:** ratio 0.85 → **crisis (0.0)** directly from trend. Sentiment is irrelevant; trend is broken.

## Backtest note

Historical Fear & Greed and funding are not in the MCP "latest" tools, so the included backtester reads them
from `fear_greed` / `funding_rate` / `oi_change` columns in the price CSV, and computes the trend from an
equal-weight index of the universe. The skill fills `regime.inputs` from the MCP tools above when live. Same
rules, two data sources — see `cmc-data-map.md`.
