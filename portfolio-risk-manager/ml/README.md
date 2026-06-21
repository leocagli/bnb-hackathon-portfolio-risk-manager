# ML regime / crash classifier

An **optional** machine-learning layer for the risk skill: a Random Forest that predicts near-term crash
probability from CoinMarketCap-style features and uses it to set exposure. Implemented **from scratch in pure
standard library** (CART + bagging) — no numpy, no scikit-learn, no install.

```bash
cd portfolio-risk-manager/ml
python ml_regime.py
```

## Why it exists

The hand-written trend-led rules are the robust default. This module answers a sharper question — *can a
learned model do better, and can we prove it honestly?* It demonstrates the ML workflow you'd actually trust:
feature engineering, a forward-looking label, leakage-free validation, feature importance, and a distilled
interpretable model — then an out-of-sample backtest of **Rules vs ML** on the same risk machinery.

## Method (the parts that make it credible)

| Step | What | Why |
|------|------|-----|
| **Features** | 16 signals from CMC data: Fear & Greed (+Δ), funding, OI, multi-horizon momentum, distance from MA50/MA200, RSI, realized vol (10/30d) + vol ratio, breadth, max pairwise correlation, drawdown-from-peak | These are the precursors of risk; all computed with **no lookahead** |
| **Label** | `1` if a drawdown ≥ 15% occurs within the next 20 days | Forward-looking, directly risk-relevant |
| **Model** | Random Forest (25 CART trees, bagging + random feature subsets, Gini) | Non-linear, handles interactions, gives feature importance |
| **Validation** | **Walk-forward** with a **purge gap** of 20 days between train and test | Time series MUST NOT use random k-fold — it leaks the future into the past. Purge removes training samples whose label window overlaps the test set |
| **Use** | Out-of-sample `p(crash)` → exposure buckets (mirrors `exposure_by_regime`), acting on the **prior** day's prediction | No lookahead in the backtest either |
| **Distillation** | A depth-3 tree printed as human-readable rules | The model stays auditable, not a black box |

> ⚠️ **The single most important point:** for financial time series, never validate with random/shuffled
> train-test splits or k-fold — it leaks future information and reports fantasy accuracy. Use walk-forward
> (expanding window) with a purge gap, as done here.

## Representative output

```
  Label       : forward 20d drawdown >= 15%   (base rate ~27%)
  Validation  : walk-forward, purge gap 20d, test step 200d (no leakage)

  OOS classification (1580 days, 8 folds):
     AUC=0.574   accuracy=0.716   precision=0.348   recall=0.056

  Top feature importances (Gini, out-of-sample forests):
     dist_ma200  15.7% | ret_60d 10.5% | vol_30d 9.0% | vol_10d 8.4% | max_pairwise_corr 8.0%

  Distilled rule (highest-risk leaf):
     near highs (small drawdown-from-peak) + rising vol ratio + correlation spike (>0.87)
       -> p(crash) = 0.54

  OUT-OF-SAMPLE BACKTEST (walk-forward test region):
  Metric            Buy&Hold     Rules    ML overlay
  Sharpe                0.03     -0.41          0.42
  Max drawdown         88.5%     17.3%         20.6%
```

## How to read this (honest interpretation)

- **AUC ≈ 0.57 is modest but real** — crash timing is genuinely hard; a model that claimed AUC 0.95 would be
  leaking. The signal is enough to *trim* exposure on elevated probability, which is what the bucketed
  mapping does.
- The **distilled rule matches intuition**: highest crash risk near the highs with rising volatility and a
  **correlation spike** (diversification quietly disappearing) — a textbook pre-crash setup. The model
  recovered structure we'd recognize, which is the point of distillation.
- **On this dataset the ML overlay beats the reactive rules out-of-sample** (Sharpe 0.42 vs −0.41). The
  regime-switching tape whipsaws trend-following; a precursor-trained classifier de-risks earlier. This is
  a *harder* dataset than the single-crash showcase in `../backtest/` (where the rules score Sharpe 1.13) —
  which is exactly why it’s a fair stress test for ML.
- **Conclusion:** ML is a useful **complement** to the rules, not a replacement — and only after walk-forward
  validation like this. The rules remain the robust, zero-dependency default.

## The synthetic data, stated plainly

`build_regime_switching` (in `../backtest/backtest.py`) is a 3-state bull/chop/bear Markov model where the
probability of entering a crash **rises with froth** (recent run-up + elevated volatility) — mirroring how
real crashes follow leverage/euphoria build-ups. We embed that structure on purpose so there is something
real to learn; the test is whether walk-forward ML can **recover** it out-of-sample (it can, partially).

## Training on real CMC history

Replace the generator with real data: pull OHLCV (`cmc-api-crypto`), Fear & Greed and derivatives history
(`cmc-api-market`), format as the CSV in `../backtest/README.md`, and feed it to `build_dataset()`. The
feature engineering, label, walk-forward, and distillation are unchanged.

## Artifact

The run writes `exposure_rules.json` — the distilled model summary (label definition, validation, top
features, and the `p(crash) → exposure` mapping) — ready to embed as an ML-backed variant of the regime
block in `portfolio_risk_spec.json`.

---

# Volatility forecaster for portfolio rotation (`vol_forecast.py`)

A second, complementary model: an **ATR-based Ridge regression** that forecasts each asset's forward realized
volatility, used to size and rotate the portfolio. Pure stdlib (own normal-equations solver, no numpy).

```bash
python vol_forecast.py
```

## Method

| Step | What |
|------|------|
| **ATR** | True Range from OHLC, smoothed over 14 days, expressed as ATR% of price (real ATR, not a close-only proxy) |
| **Features** | `atr_pct`, realized vol 10/30d, vol ratio, ATR expansion, mean abs return, RSI distance from 50, market (index) vol |
| **Target** | forward 10-day annualized realized volatility |
| **Model** | Ridge regression (standardized features, closed-form), trees of validation done **walk-forward** (no leakage) |
| **Baselines** | random walk (use trailing 30d vol as the forecast) and EWMA(0.94) |
| **Use** | inverse-**forecast**-vol rotation + vol targeting, vs inverse-**trailing**-vol — same machinery, signal swapped |

## Representative output

```
  OOS forecast accuracy (9540 samples):
     model               R2     RMSE(vol)
     Ridge+ATR        0.094         0.241
     RandomWalk rv30 -0.283         0.286
     EWMA(0.94)      -0.170         0.273

  Feature influence: index_rv_30d 21% | rv_10d 19% | rv_30d 18% | vol_ratio 17% | atr_expansion 14% | atr_pct 7%

  ROTATION BACKTEST (out-of-sample, vol target 40%):
  Metric                Trailing-vol   Forecast-vol
  Ann. vol (realized)         36.5%          35.2%
  Sharpe                       0.70           0.64
  Max drawdown                27.6%          26.0%
```

## Honest interpretation

- **The regression is the only forecaster with R² > 0.** Trailing 30d vol (the common default) and EWMA both
  have *negative* R² here — across regime shifts, last month's vol is actively misleading. ATR + market vol +
  the vol ratio carry real leading information.
- **ATR contributes but isn't dominant** — realized and market volatility lead, ATR expansion adds
  incremental signal. That's the honest picture; we don't overstate ATR.
- **The forecast's payoff is risk control, not return.** In rotation it targets vol more tightly and cuts
  drawdown; Sharpe is roughly flat. That is exactly what a volatility model should deliver — better-behaved
  risk, not a return edge. Use it to feed the overlay's `target_portfolio_vol` scaling and inverse-vol
  weighting.

For real data, use CMC OHLCV (`cmc-api-crypto`, which already has high/low) and skip the synthetic OHLC step.
Writes `vol_forecast_model.json` summarizing the validated model.
