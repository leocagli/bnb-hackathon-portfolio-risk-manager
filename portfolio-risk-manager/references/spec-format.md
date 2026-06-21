# `portfolio_risk_spec.json` — Field Reference

The spec is the deliverable. It is fully self-contained: a backtester needs only this file plus a price
series. Validated by `schema/portfolio_risk_spec.schema.json`. All fields below have documented defaults so
the skill can always emit a complete spec.

## Top level

| Field          | Type   | Default | Notes                                                        |
|----------------|--------|---------|--------------------------------------------------------------|
| `spec_version` | string | "1.0"   | Schema version.                                              |
| `name`         | string | —       | Human label for this risk profile.                           |
| `generated_at` | string | —       | ISO-8601 timestamp when the skill produced the spec.         |
| `universe`     | array  | —       | Asset symbols, e.g. `["ETH","LINK","UNI","AAVE","CAKE","AVAX"]`. |
| `base_capital_usd` | number | 10000 | Starting capital for the backtest.                        |
| `assumptions`  | array  | []      | Strings recording any defaults used because data was missing.|

## `regime`

| Field                  | Type   | Default | Notes                                                 |
|------------------------|--------|---------|-------------------------------------------------------|
| `current`              | enum   | "neutral" | `risk_on \| neutral \| risk_off \| crisis`.         |
| `inputs`               | object | {}      | The live values used (fear_greed, funding_rate_8h, btc_dominance, altseason_index, market_rsi, trend). |
| `exposure_by_regime`   | object | see below | Max gross exposure per regime label.               |

Default `exposure_by_regime`: `{"risk_on":1.0,"neutral":0.65,"risk_off":0.30,"crisis":0.0}`.
See `regime-detection.md` for how `current` is scored.

## `sizing`

| Field                        | Type   | Default      | Notes                                       |
|------------------------------|--------|--------------|---------------------------------------------|
| `method`                     | enum   | "inverse_vol"| `equal_weight \| inverse_vol \| risk_parity_lite`. |
| `target_portfolio_vol_annual`| number | 0.40         | Annualized vol target (0.40 = 40%).         |
| `vol_lookback_days`          | int    | 30           | Window for realized vol.                     |
| `max_vol_scalar`             | number | 2.0          | Cap on vol-targeting leverage.               |
| `max_weight_per_asset`       | number | 0.25         | Per-asset cap within the risky sleeve.       |
| `min_weight_per_asset`       | number | 0.0          | Floor (0 = an asset can be dropped).         |
| `trend_filter`               | object | `{enabled:true, ma_days:50}` | Drop assets below their own `ma_days` moving average. |

## `correlation`

| Field          | Type   | Default            | Notes                                          |
|----------------|--------|--------------------|------------------------------------------------|
| `lookback_days`| int    | 45                 | Window for the correlation matrix.             |
| `max_pairwise` | number | 0.75               | Pairs above this are treated as a cluster.     |
| `penalty`      | enum   | "downweight_cluster" | `downweight_cluster \| cap_cluster \| none`. |

## `limits`

| Field               | Type   | Default | Notes                               |
|---------------------|--------|---------|-------------------------------------|
| `max_gross_exposure`| number | 1.0     | Ceiling on invested fraction.       |
| `max_assets`        | int    | 8       | Max simultaneous positions.         |
| `leverage`          | number | 1.0     | >1.0 only if explicitly allowed.    |

## `drawdown_control`

| Field            | Type   | Default | Notes                                                       |
|------------------|--------|---------|------------------------------------------------------------|
| `throttle`       | array  | see below | Ordered `{dd_gte, exposure_mult}`; deepest breached wins. |
| `kill_switch_dd` | number | 0.25    | Go to cash at this drawdown.                                |
| `reentry`        | object | see below | `{cooldown_days, recover_to_dd_lte}`.                     |

Default `throttle`: `[{"dd_gte":0.10,"exposure_mult":0.5},{"dd_gte":0.15,"exposure_mult":0.25}]`.
Default `reentry`: `{"cooldown_days":3,"recover_to_dd_lte":0.08}`.

## `event_risk`

| Field                                   | Type   | Default | Notes                               |
|-----------------------------------------|--------|---------|-------------------------------------|
| `enabled`                               | bool   | true    | Toggle event de-risking.            |
| `derisk_before_high_impact_event_hours` | int    | 24      | Window before a catalyst.           |
| `exposure_mult_during_event_window`     | number | 0.5     | Multiplier inside the window.        |

## `execution`

| Field                          | Type   | Default                  | Notes                                     |
|--------------------------------|--------|--------------------------|-------------------------------------------|
| `smoothing_mode`               | enum   | "asymmetric_fast_down"   | `none \| symmetric \| asymmetric_fast_down`. |
| `exposure_smoothing_span_days` | int    | 5                        | EMA span for exposure smoothing.          |

`asymmetric_fast_down` cuts exposure instantly but eases back in over the EMA span — reduces turnover and
whipsaw without delaying protection. See `exposure-and-limits.md` §7.

## `idiosyncratic_flags`

| Field                    | Type   | Default  | Notes                                          |
|--------------------------|--------|----------|------------------------------------------------|
| `max_whale_concentration`| number | 0.30     | Cap/exclude tokens above this top-holder share.|
| `min_24h_volume_usd`     | number | 5000000  | Liquidity floor for inclusion.                 |

## `rebalance`

| Field          | Type   | Default | Notes                                            |
|----------------|--------|---------|--------------------------------------------------|
| `frequency_days` | int  | 7       | How often target weights are recomputed.         |
| `drift_band`   | number | 0.05    | Optional: rebalance early if a weight drifts this far. |

## Minimal valid spec

Every block except `name`, `generated_at`, and `universe` may be omitted and the backtester will apply the
defaults above — but the skill should emit the full spec for transparency. The example in
`examples/sample_risk_spec.json` is complete.
