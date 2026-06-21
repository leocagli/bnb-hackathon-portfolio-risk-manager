# Sizing, Correlation & Limits

Once the regime sets the **risk budget** (max gross exposure), this layer decides how that budget is split
across assets and what caps prevent concentration.

## 0. Asset-level trend filter (dual-momentum lite)

Before sizing, drop any asset trading **below its own moving average** (`sizing.trend_filter.ma_days`,
default 50). You only hold assets that are trending up; falling names are excluded until they reclaim their
average. This is the largest single contributor to risk-adjusted return after the regime budget: it raises
mean return (no dead weight) and cuts volatility and drawdown (no catching knives). If every asset is below
its average, the sleeve is empty and the portfolio sits in cash. Set `enabled: false` to disable.

## 1. Inverse-volatility sizing (default)

Give more weight to calmer assets so each contributes roughly equal risk.

```
raw_weight_i = 1 / vol_i           # vol_i = annualized realized vol over `vol_lookback_days`
weight_i     = raw_weight_i / sum(raw_weight_j)
```

Alternatives the spec supports (`sizing.method`):

- `equal_weight` — `weight_i = 1 / N`. Fallback when per-asset vol is unavailable.
- `inverse_vol` — as above (default; robust, no return forecast needed).
- `risk_parity_lite` — inverse-vol then one correlation adjustment pass (see below).

> **Forecast vs trailing vol:** by default `vol_i` is *trailing* realized vol. The optional ATR-based Ridge
> forecaster (`../ml/vol_forecast.py`) supplies a *forward* vol estimate that leads regime shifts (trailing
> vol lags and can be actively misleading across them). Swapping the forecast in here tightens vol targeting
> and lowers drawdown — see `../ml/README.md`.

## 2. Volatility targeting

Inverse-vol sets *relative* weights; vol targeting sets the *overall* size so the portfolio aims at a chosen
risk level:

```
realized_port_vol = annualized stdev of the sized sleeve's daily returns over `vol_lookback_days`
vol_scalar        = clamp(target_portfolio_vol_annual / realized_port_vol, 0, max_vol_scalar)
```

`max_vol_scalar` (default 1.5) caps how much the strategy can lever up calm periods. The final gross is:

```
gross = min(max_gross_exposure, regime_budget * vol_scalar) * drawdown_throttle * event_mult
```

## 3. Per-asset cap

No single asset may exceed `sizing.max_weight_per_asset` (default 0.25) of the risky sleeve. After capping,
re-normalize the remaining weights. This prevents one volatile name from dominating even if inverse-vol
would have allowed it (e.g., a temporarily calm but fragile token).

## 4. Correlation cap (hidden concentration)

Two assets that move together are effectively one position. Compute the pairwise correlation matrix over
`correlation.lookback_days` (default 45). For any pair above `correlation.max_pairwise` (default 0.75):

- `penalty = "downweight_cluster"` (default): identify the correlated cluster and scale every member's
  weight by `1 / sqrt(cluster_size)`, then re-normalize. This keeps diversification benefit honest.
- `penalty = "cap_cluster"`: cap the *combined* weight of the cluster at `max_weight_per_asset`.

Correlation is also informed qualitatively by `trending_crypto_narratives`: assets in the same hot narrative
are typically correlated, so treat a shared narrative as a prior toward down-weighting.

## 5. Hard limits

| Limit                      | Default | Meaning                                            |
|----------------------------|---------|----------------------------------------------------|
| `limits.max_gross_exposure`| 1.00    | Ceiling on total invested fraction (1.0 = no leverage) |
| `limits.max_assets`        | 8       | Cap on simultaneous positions (operational simplicity) |
| `limits.leverage`          | 1.00    | >1.0 only if the venue and risk appetite allow it  |

## 6. Idiosyncratic flags (single-name risk)

From `get_crypto_metrics` and `get_crypto_quotes_latest`:

- `idiosyncratic_flags.max_whale_concentration` (default 0.30): if the top holders control more than this
  share, cap the asset at half `max_weight_per_asset` (or exclude if `> 0.5`). Whale-heavy tokens can be
  dumped on the book instantly.
- `idiosyncratic_flags.min_24h_volume_usd` (default 5,000,000): exclude assets thinner than this — you can't
  size what you can't exit.

## 7. Exposure smoothing (reduce whipsaw)

Daily exposure changes create turnover and whipsaw, which drag on net Sharpe. `execution.smoothing_mode`
controls how the final gross is smoothed across days using an EMA of span
`execution.exposure_smoothing_span_days` (default 5):

- `asymmetric_fast_down` (default): **cut instantly, re-risk gradually.** If today's target gross is lower
  than yesterday's, apply it immediately (protection is never delayed); if higher, ease in via the EMA. This
  captures the turnover benefit without slowing down de-risking — the best of both.
- `symmetric`: EMA in both directions (smoother, but delays de-risking — generally worse for drawdown).
- `none`: use the raw target gross.

## Ordering of operations (deterministic)

1. Drop assets **below their trend filter** and those failing liquidity / whale flags.
2. Compute inverse-vol raw weights over the survivors.
3. Apply per-asset cap, re-normalize.
4. Apply correlation down-weighting, re-normalize.
5. Compute portfolio vol scalar (vol targeting).
6. Multiply by regime budget, drawdown throttle, event multiplier → raw gross.
7. Cap raw gross at `max_gross_exposure`; apply exposure smoothing → final gross. Remainder is cash.

This order is fixed so the spec is reproducible and the backtest matches the live skill exactly.
