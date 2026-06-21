# Backtest harness

Proves that `portfolio_risk_spec.json` is genuinely backtestable. Pure Python standard library — **no
dependencies**.

## Run

```bash
cd portfolio-risk-manager/backtest

# single canonical path (bull -> crash -> recovery)
python backtest.py --spec ../examples/sample_risk_spec.json

# Monte Carlo robustness: 200 synthetic paths with jittered crash timing
python backtest.py --mc 200
```

The single run generates a deterministic synthetic dataset (seed 42) at `data/prices_sample.csv` and prints a
side-by-side comparison of an equal-weight buy-and-hold baseline vs. the risk overlay defined by the spec.

### Flags

| Flag     | Default                      | Meaning                                            |
|----------|------------------------------|----------------------------------------------------|
| `--spec` | `../examples/sample_risk_spec.json` | Risk spec to test.                          |
| `--data` | synthetic                    | CSV of prices + regime columns (see format below). |
| `--out`  | none                         | Write both equity curves to a CSV.                 |
| `--mc N` | off                          | Run N synthetic paths and report aggregate stats.  |

## Expected output — single canonical path

```
  Metric                     Buy&Hold (EW)      Risk Overlay
  Total return                       37.9%             35.5%
  CAGR                               24.3%             22.8%
  Annualized vol                     64.7%             19.9%
  Sharpe                              0.66              1.13
  Max drawdown                       69.2%             12.3%
  Calmar (CAGR/MDD)                   0.35              1.85
  Time in market                    100.0%             49.7%
```

## Expected output — Monte Carlo (200 paths)

```
  Metric (mean / median)             Buy&Hold          Overlay
  Sharpe                        0.84 /  0.76     1.30 /  1.40
  Max drawdown                          72.9%            15.6%
  Calmar                                 1.18             1.88
  Overlay beat Buy&Hold on Sharpe in 132/200 paths (66%).
  Mean Sharpe uplift: +0.46   Mean drawdown cut: 57.3%
```

The overlay nearly matches buy-and-hold's return while cutting max drawdown from ~69% to ~12% and lifting
Sharpe 0.66 → 1.13 on the canonical path. Across 200 randomized paths it beats buy-and-hold on Sharpe ~2/3
of the time with a +0.46 mean Sharpe uplift — the gain is robust, not a single lucky path. The losses are
mostly smooth-bull paths where 100%-invested buy-and-hold wins on Sharpe despite far larger drawdowns.

## CSV format

One row per day. Price columns must match the spec's `universe` exactly.

```
date,ETH,LINK,UNI,AAVE,CAKE,AVAX,fear_greed,funding_rate,oi_change
D0000,3000,15,8,90,2,30,52,0.01,5
...
```

| Column        | Meaning                                                              |
|---------------|---------------------------------------------------------------------|
| `date`        | Any sortable label (rows are assumed chronological).                |
| `<ASSET>`     | Close price for each asset in `universe`.                           |
| `fear_greed`  | Fear & Greed index 0–100 (CMC `get_global_metrics_latest`).         |
| `funding_rate`| Perp funding, 8h, in **percent** (0.06 = 0.06%) (CMC derivatives).  |
| `oi_change`   | Open-interest % change (CMC derivatives). Optional; defaults to 0.  |

## What the harness implements (matches the spec, no lookahead)

For each day, using only information available the prior day:

1. **Regime (trend-led)** from index trend, with `funding_rate`/`oi_change` and `fear_greed` trimming at
   extremes (`references/regime-detection.md`) → sets the gross-exposure budget.
2. **Trend filter** — drop assets below their own moving average (`sizing.trend_filter`).
3. **Sizing** — inverse-volatility weights, per-asset cap, correlation cluster down-weighting, then
   volatility targeting toward `target_portfolio_vol_annual` (`references/exposure-and-limits.md`).
4. **Drawdown control** — throttle ladder, kill-switch to cash, and cooldown re-entry with high-water-mark
   reset (`references/drawdown-control.md`).
5. **Exposure smoothing** — `execution.smoothing_mode` (default cut-fast/re-risk-slow) reduces whipsaw.
6. Rebalances target weights every `rebalance.frequency_days`; scales gross exposure daily.

`event_risk` is honored in the live skill; the synthetic run leaves it off (no event schedule), so the
`event_mult` is 1.0.

## Backtesting on real CMC data

Replace the synthetic CSV with real history:

- **Prices (OHLCV):** pull via the `cmc-api-crypto` skill's OHLCV endpoint.
- **Fear & Greed:** `cmc-api-market` fear-greed endpoint.
- **Funding / open interest:** `cmc-api-market` / derivatives endpoints.

Format the columns as above and pass `--data your_history.csv`. The exact same rules run — only the data
source changes. Note the synthetic dataset is intentionally constructed (a clean bull → crash → recovery) to
exercise every rule; real-data results will be noisier and less dramatic.
