# CMC Data → Risk Spec Mapping

Exactly which CoinMarketCap MCP tool feeds which part of the spec. This is what makes the skill a heavy,
legitimate user of the CMC Agent Hub (relevant for the "Best Use of Agent Hub" bonus).

## Market-wide (regime block)

| MCP tool                                   | Fields consumed                                   | Spec target                         |
|--------------------------------------------|---------------------------------------------------|-------------------------------------|
| `get_global_metrics_latest`                | Fear & Greed, BTC/ETH dominance, altseason index, total mcap change, ETF flows | `regime.inputs`, sentiment sub-score |
| `get_global_crypto_derivatives_metrics`    | funding rate (8h), open interest change, liquidation skew | `regime.inputs.funding_rate_8h`, crowding sub-score |
| `get_crypto_marketcap_technical_analysis`  | total-mcap RSI, MACD, position vs 200d MA          | `regime.inputs.market_rsi`, `regime.inputs.trend`, trend sub-score |

## Per-asset (sizing / correlation / flags)

| MCP tool                          | Fields consumed                                  | Spec target                                |
|-----------------------------------|--------------------------------------------------|--------------------------------------------|
| `search_cryptos`                  | id, symbol, slug, rank                            | resolve `universe` → CMC IDs               |
| `get_crypto_quotes_latest`        | price, 24h volume, % changes (1h/24h/7d/30d/90d/1y) | recent-return proxy, `idiosyncratic_flags.min_24h_volume_usd` |
| `get_crypto_technical_analysis`   | RSI, SMA/EMA, ATR-style volatility, pivots        | inverse-vol sizing input, vol targeting    |
| `get_crypto_metrics`              | whale concentration, holder distribution          | `idiosyncratic_flags.max_whale_concentration` |

## Forward-looking (event risk)

| MCP tool                       | Fields consumed                          | Spec target                       |
|--------------------------------|------------------------------------------|-----------------------------------|
| `get_upcoming_macro_events`    | event date, impact level, type            | `event_risk` window + multiplier  |
| `trending_crypto_narratives`   | narrative membership of universe assets    | prior for `correlation` cap       |

## Live vs backtest

The MCP tools return the **latest** snapshot — perfect for generating a spec *today*. Backtesting needs a
*history*. The two share the same logic but read different sources:

| Quantity        | Live (skill)                              | Backtest (`backtest.py`)            |
|-----------------|-------------------------------------------|-------------------------------------|
| Prices          | `get_crypto_quotes_latest` (point in time)| `price` columns in the CSV          |
| Per-asset vol   | `get_crypto_technical_analysis`           | rolling stdev of CSV returns        |
| Correlation     | derived / narratives prior                | rolling corr of CSV returns         |
| Fear & Greed    | `get_global_metrics_latest`               | `fear_greed` column in the CSV      |
| Funding rate    | `get_global_crypto_derivatives_metrics`   | `funding_rate` column in the CSV    |

To backtest on **real** CMC history, pull OHLCV via the `cmc-api-crypto` skill's OHLCV endpoint and the
Fear & Greed / derivatives history via `cmc-api-market`, then format as the CSV described in
`backtest/README.md`. The thresholds in `regime-detection.md` apply identically to both.
