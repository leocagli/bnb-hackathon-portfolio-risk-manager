# BNB HACK: AI Trading Agent Edition — Track 2 Submission

**Portfolio Risk Manager** — a CoinMarketCap Strategy Skill  
Track 2 · Strategy Skills powered by CMC · [DoraHacks submission](https://dorahacks.io/hackathon/bnbhack-twt-cmc/tracks)

---

## Quick start

```bash
git clone https://github.com/leocagli/bnb-hackathon-portfolio-risk-manager
cd bnb-hackathon-portfolio-risk-manager/portfolio-risk-manager

# run the backtest (no install — pure Python stdlib)
cd backtest
python backtest.py --spec ../examples/sample_risk_spec.json   # canonical path
python backtest.py --mc 200                                   # Monte Carlo 200 paths

# optional ML layer
cd ../ml
python ml_regime.py      # Random Forest crash classifier
python vol_forecast.py   # ATR Ridge volatility forecaster
```

---

## Install the skill in your CMC-compatible agent

### 1. Copy the skill folder

```bash
cp -r portfolio-risk-manager /path/to/your/skills/
```

### 2. Configure the CMC MCP server

Add to your agent's MCP config (e.g. `claude_desktop_config.json` or `.mcp.json`):

```json
{
  "mcpServers": {
    "cmc-mcp": {
      "url": "https://mcp.coinmarketcap.com/mcp",
      "headers": {
        "X-CMC-MCP-API-KEY": "YOUR_CMC_API_KEY"
      }
    }
  }
}
```

Get your API key at https://pro.coinmarketcap.com/login (free tier works).

### 3. Invoke the skill

Trigger phrases (the agent will pick up the skill automatically):

```
"build me a risk spec for ETH, LINK, AAVE, UNI"
"size my portfolio with a 40% vol target"
"generate a drawdown protection overlay"
/portfolio-risk-manager
```

The skill will:
1. Pull live data via the 9 declared CMC MCP tools
2. Classify the market regime (trend-led)
3. Produce a `portfolio_risk_spec.json`
4. Print the backtest command to validate it

---

## Alternative: x402 (keyless, pay-per-request)

No API key needed. Each CMC data call costs **0.01 USDC on Base**:

```http
GET https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest
X-Payment: <base64-encoded USDC payment proof on Base>
```

See [`portfolio-risk-manager/references/data-access.md`](portfolio-risk-manager/references/data-access.md) for full x402 + CLI docs.

---

## What the skill produces

A single `portfolio_risk_spec.json` validated by [`schema/portfolio_risk_spec.schema.json`](portfolio-risk-manager/schema/portfolio_risk_spec.schema.json):

| Block | Controls |
|---|---|
| `regime` | Market regime (trend-led) → max gross exposure |
| `sizing` | Inverse-vol weighting + vol targeting to 40% ann. |
| `correlation` | Cluster down-weighting (hidden concentration) |
| `limits` | Per-asset 25% cap, max 8 positions |
| `drawdown_control` | Throttle ladder → kill-switch at −25% |
| `event_risk` | Cut exposure around macro catalysts |
| `execution` | Asymmetric smoothing: cut fast, re-risk slow |
| `idiosyncratic_flags` | Whale concentration + liquidity floors |

**Backtest results (canonical path):**

| Metric | Buy & Hold | Risk Overlay |
|---|---|---|
| Sharpe | 0.66 | **1.13** |
| Max drawdown | 69.2% | **12.3%** |
| Calmar | 0.35 | **1.85** |

Monte Carlo (200 paths): overlay beats buy-and-hold on Sharpe in **66% of paths**, mean DD cut 57pp.

---

## Slides

Open [`portfolio-risk-manager/slides/index.html`](portfolio-risk-manager/slides/index.html) in any browser — no server needed.

---

## License

MIT
