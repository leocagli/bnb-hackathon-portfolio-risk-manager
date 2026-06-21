# Data Access — three routes into the CMC Agent Hub

This skill is built on the **CoinMarketCap AI Agent Hub** and supports its three agent-native access routes.
The default is MCP; x402 and the CLI are drop-in alternatives for the same data, so the skill works whether
the agent has an API key, a funded wallet, or just a terminal.

## 1. MCP (default)

Real-time tools over the Model Context Protocol. This is what `allowed-tools` in `SKILL.md` declares.

```json
{
  "mcpServers": {
    "cmc-mcp": {
      "url": "https://mcp.coinmarketcap.com/mcp",
      "headers": { "X-CMC-MCP-API-KEY": "your-api-key" }
    }
  }
}
```

The nine tools used by this skill (regime, sizing, flags, events):
`search_cryptos`, `get_crypto_quotes_latest`, `get_crypto_technical_analysis`, `get_crypto_metrics`,
`get_global_metrics_latest`, `get_global_crypto_derivatives_metrics`,
`get_crypto_marketcap_technical_analysis`, `get_upcoming_macro_events`, `trending_crypto_narratives`.

## 2. x402 (pay-per-request, no API key)

For autonomous agents that pay per call instead of holding a key: x402 settles **0.01 USDC per request on
Base** (chain id 8453). Useful for keyless, on-the-fly data pulls in an agent flow.

```bash
npm install @x402/axios @x402/evm viem
# fund a wallet with USDC on Base; export its key as an env var (keep it secure)
```

Then request the same CMC endpoints through the x402 axios client (see the official `cmc-x402` skill for the
full client setup). When MCP is unavailable, the skill can fetch the regime and per-asset inputs over x402
and assemble the identical `portfolio_risk_spec.json`.

## 3. CLI / REST (direct integration)

For scripted or IDE workflows, hit the REST API directly:

```
Base URL : https://pro-api.coinmarketcap.com
Auth     : X-CMC_PRO_API_KEY: your-api-key
```

This is also the route used to pull **historical** data for backtesting and ML training (the MCP "latest"
tools are point-in-time): OHLCV via the `cmc-api-crypto` endpoints, Fear & Greed and derivatives history via
`cmc-api-market`. Format the result as the CSV in `../backtest/README.md`.

## Route selection

| Situation                                  | Route  |
|--------------------------------------------|--------|
| Interactive agent with an API key          | MCP    |
| Autonomous agent, keyless, pays per call   | x402   |
| Scripts / IDE / fetching history to backtest | CLI / REST |

All three return the same fields and feed the same spec — only the transport differs.
