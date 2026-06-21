#!/usr/bin/env python3
"""
Backtester for the portfolio-risk-manager CMC skill.

Takes a `portfolio_risk_spec.json` (the skill's deliverable) and a multi-asset price series, then runs the
full portfolio-level risk overlay against an equal-weight buy-and-hold baseline. Reports CAGR, annualized
volatility, Sharpe, max drawdown, Calmar, and time-in-market for both, so the value of the risk layer is
measurable.

Pure Python standard library only -- no numpy/pandas.

Single backtest (synthetic data if --data omitted):
    python backtest.py --spec ../examples/sample_risk_spec.json

Monte Carlo robustness (N synthetic paths, aggregate stats) -- proves the Sharpe gain is not curve-fit:
    python backtest.py --mc 200

CSV format (one row per day):
    date,<ASSET1>,<ASSET2>,...,fear_greed,funding_rate,oi_change
e.g.
    2025-01-01,3000,15,8,90,2,30,52,0.01,5
"""

import argparse
import csv
import json
import math
import os
import random
import statistics

ANN = 365  # crypto trades every day


# --------------------------------------------------------------------------------------------------
# Stats helpers (stdlib only)
# --------------------------------------------------------------------------------------------------
def stdev(xs):
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def mean(xs):
    return statistics.mean(xs) if xs else 0.0


def median(xs):
    return statistics.median(xs) if xs else 0.0


def pearson(a, b):
    n = len(a)
    if n < 2:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((a[i] - ma) ** 2 for i in range(n))
    vb = sum((b[i] - mb) ** 2 for i in range(n))
    if va <= 0 or vb <= 0:
        return 0.0
    return cov / math.sqrt(va * vb)


def rsi(values, period=14):
    if len(values) <= period:
        return 50.0
    gains, losses = [], []
    for i in range(len(values) - period, len(values)):
        ch = values[i] - values[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag, al = sum(gains) / period, sum(losses) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def sma(values, t, window):
    """Mean of `values` over the `window` days ending at t-1 (no lookahead)."""
    lo = max(0, t - window)
    seg = values[lo:t]
    return sum(seg) / len(seg) if seg else values[t - 1]


# --------------------------------------------------------------------------------------------------
# Spec loading with defaults
# --------------------------------------------------------------------------------------------------
DEFAULTS = {
    "base_capital_usd": 10000,
    "regime": {
        "exposure_by_regime": {"risk_on": 1.0, "neutral": 0.65, "risk_off": 0.30, "crisis": 0.0}
    },
    "sizing": {
        "method": "inverse_vol",
        "target_portfolio_vol_annual": 0.40,
        "vol_lookback_days": 30,
        "max_vol_scalar": 2.0,
        "max_weight_per_asset": 0.25,
        "min_weight_per_asset": 0.0,
        "trend_filter": {"enabled": True, "ma_days": 50},
    },
    "correlation": {"lookback_days": 45, "max_pairwise": 0.75, "penalty": "downweight_cluster"},
    "limits": {"max_gross_exposure": 1.0, "max_assets": 8, "leverage": 1.0},
    "drawdown_control": {
        "throttle": [{"dd_gte": 0.10, "exposure_mult": 0.5}, {"dd_gte": 0.15, "exposure_mult": 0.25}],
        "kill_switch_dd": 0.25,
        "reentry": {"cooldown_days": 3, "recover_to_dd_lte": 0.08},
    },
    "execution": {"smoothing_mode": "asymmetric_fast_down", "exposure_smoothing_span_days": 5},
    "rebalance": {"frequency_days": 7, "drift_band": 0.05},
}


def merged(spec, key):
    out = dict(DEFAULTS.get(key, {}))
    out.update(spec.get(key, {}) or {})
    return out


# --------------------------------------------------------------------------------------------------
# Synthetic data generation (deterministic per seed)
# --------------------------------------------------------------------------------------------------
# Factor loadings per asset. UNI/CAKE/AAVE share a "defi" factor -> correlated cluster.
ASSET_META = {
    "ETH":  {"price": 3000.0, "beta": 1.00, "defi": 0.0, "idio": 0.018},
    "LINK": {"price": 15.0,   "beta": 1.20, "defi": 0.0, "idio": 0.030},
    "UNI":  {"price": 8.0,    "beta": 1.25, "defi": 0.6, "idio": 0.015},
    "AAVE": {"price": 90.0,   "beta": 1.20, "defi": 0.6, "idio": 0.015},
    "CAKE": {"price": 2.0,    "beta": 1.30, "defi": 0.6, "idio": 0.018},
    "AVAX": {"price": 30.0,   "beta": 1.15, "defi": 0.0, "idio": 0.030},
}


def _meta(universe):
    m = dict(ASSET_META)
    for a in universe:
        m.setdefault(a, {"price": 10.0, "beta": 1.0, "defi": 0.0, "idio": 0.03})
    return m


def _derive_columns(prices, universe):
    """Derive Fear&Greed / funding / OI-change columns from the equal-weight index path (shared logic)."""
    n = len(prices[universe[0]])
    base = {a: prices[a][0] for a in universe}
    idx = [sum(prices[a][t] / base[a] for a in universe) / len(universe) for t in range(n)]

    def tr(t, k):
        return idx[t] / idx[t - k] - 1.0 if t >= k else 0.0

    def clamp(x, lo, hi):
        return max(lo, min(hi, x))

    fng, funding, oi, dates = [], [], [], []
    for t in range(n):
        fng.append(round(clamp(50.0 + 320.0 * tr(t, 20), 5.0, 95.0), 1))
        funding.append(round(clamp(0.6 * tr(t, 10), -0.04, 0.08), 4))
        oi.append(round(clamp(300.0 * tr(t, 10), -50.0, 50.0), 1))
        dates.append(f"D{t:04d}")
    return dates, fng, funding, oi


def build_synthetic(universe, n=540, seed=42, jitter=False):
    """Return (dates, prices, fng, funding, oi) in memory. Bull -> ~55% crash -> recovery.

    jitter=False gives the canonical path (fixed phase timing) used for the single-path showcase.
    jitter=True varies the crash timing per seed -- used by Monte Carlo so robustness is not an
    artifact of the crash always landing on the same day.
    """
    rng = random.Random(seed)
    meta = _meta(universe)
    bull_end = 260 + (rng.randint(-30, 30) if jitter else 0)
    crash_end = bull_end + 60 + (rng.randint(-15, 15) if jitter else 0)

    def phase(t):
        if t < bull_end:
            return 0.0045, 0.020          # bull
        if t < crash_end:
            return -0.013, 0.050          # crash
        return 0.0018, 0.025              # recovery

    prices = {a: [meta[a]["price"]] for a in universe}
    for t in range(1, n):
        mu, sig = phase(t)
        mkt = rng.gauss(mu, sig)
        defi = rng.gauss(0.0, 0.02)
        for a in universe:
            m = meta[a]
            prices[a].append(max(prices[a][-1] * (1.0 + m["beta"] * mkt + m["defi"] * defi
                                                  + rng.gauss(0.0, m["idio"])), 1e-6))

    dates, fng, funding, oi = _derive_columns(prices, universe)
    return dates, prices, fng, funding, oi


def build_regime_switching(universe, n=2400, seed=7):
    """Long multi-cycle path via a 3-state (bull/chop/bear) Markov model with realistic crash precursors.

    The probability of switching INTO the bear state rises with "froth" -- recent run-up (momentum) and
    elevated volatility -- exactly as real crashes tend to follow leverage/euphoria build-ups. This embeds
    a genuine, learnable signal in the features so a crash classifier can be validated out-of-sample
    against a real target (rather than memoryless noise, where nothing is predictable). Returns (dates,
    prices, fng, funding, oi, states) where states[t] is the latent market state (0 bull, 1 chop, 2 bear).
    """
    rng = random.Random(seed)
    meta = _meta(universe)
    mu = {0: 0.0040, 1: 0.0000, 2: -0.0110}
    sig = {0: 0.020, 1: 0.028, 2: 0.052}

    mkts, lvl = [], [1.0]   # market-factor returns and a market index proxy

    def bear_prob():
        if len(mkts) < 40:
            return 0.005
        mom40 = lvl[-1] / lvl[-40] - 1.0
        vol20 = stdev(mkts[-20:])
        return min(0.15, 0.004 + 1.0 * max(0.0, mom40 - 0.15) + 0.6 * max(0.0, vol20 - 0.035))

    def next_state(s):
        pb = bear_prob()
        if s == 0:
            probs = [max(0.0, 1.0 - 0.025 - pb), 0.025, pb]
        elif s == 1:
            probs = [0.040, max(0.0, 1.0 - 0.040 - pb), pb]
        else:
            probs = [0.060, 0.110, 0.830]   # bear persistence
        r, c = rng.random(), 0.0
        for j, p in enumerate(probs):
            c += p
            if r <= c:
                return j
        return 2

    state, states = 0, [0]
    prices = {a: [meta[a]["price"]] for a in universe}
    for t in range(1, n):
        state = next_state(state)               # decided from history up to t-1 (no lookahead)
        states.append(state)
        mkt = rng.gauss(mu[state], sig[state])
        mkts.append(mkt)
        lvl.append(lvl[-1] * (1.0 + mkt))
        defi = rng.gauss(0.0, 0.02)
        for a in universe:
            m = meta[a]
            prices[a].append(max(prices[a][-1] * (1.0 + m["beta"] * mkt + m["defi"] * defi
                                                  + rng.gauss(0.0, m["idio"])), 1e-6))

    dates, fng, funding, oi = _derive_columns(prices, universe)
    return dates, prices, fng, funding, oi, states


def write_csv(path, dates, prices, fng, funding, oi, universe):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fields = ["date"] + universe + ["fear_greed", "funding_rate", "oi_change"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in range(len(dates)):
            row = {"date": dates[t]}
            for a in universe:
                row[a] = round(prices[a][t], 6)
            row["fear_greed"], row["funding_rate"], row["oi_change"] = fng[t], funding[t], oi[t]
            w.writerow(row)


def load_data(path, universe):
    dates, prices = [], {a: [] for a in universe}
    fng, funding, oi = [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            dates.append(row["date"])
            for a in universe:
                prices[a].append(float(row[a]))
            fng.append(float(row.get("fear_greed", 50)))
            funding.append(float(row.get("funding_rate", 0)))
            oi.append(float(row.get("oi_change", 0)))
    return dates, prices, fng, funding, oi


# --------------------------------------------------------------------------------------------------
# Regime classification (mirrors references/regime-detection.md)
# --------------------------------------------------------------------------------------------------
REGIME_ORDER = ["risk_on", "neutral", "risk_off", "crisis"]


def _step_down(label, k=1):
    return REGIME_ORDER[min(len(REGIME_ORDER) - 1, REGIME_ORDER.index(label) + k)]


def regime_label(fng, funding, oi, index_hist):
    """Trend-led regime (see references/regime-detection.md).

    Trend is the primary axis: stay invested while the market is above its moving average; go defensive
    only when the trend breaks. Euphoria (extreme Fear & Greed) and one-sided leverage (extreme funding +
    rising OI) can only *trim* exposure one notch each -- they never force cash on their own. This keeps
    the strategy in healthy uptrends (where most of the return is) while still side-stepping the crash,
    which is what lifts risk-adjusted return.
    """
    if len(index_hist) >= 20:
        w = min(200, len(index_hist))
        ma = sum(index_hist[-w:]) / w
        ratio = index_hist[-1] / ma if ma > 0 else 1.0
        r = rsi(index_hist, 14)
    else:
        ratio, r = 1.0, 50.0

    if ratio >= 1.00:                       # confirmed uptrend
        base = "risk_on" if r < 75 else "neutral"   # blow-off RSI -> trim
    elif ratio >= 0.90:                     # mild downtrend
        base = "risk_off"
    else:                                   # deep downtrend
        base = "crisis"

    if funding > 0.05 and oi > 20:          # one-sided leverage building -> trim one notch
        base = _step_down(base)
    if fng >= 90:                           # extreme euphoria -> trim one notch
        base = _step_down(base)

    return base, 0


# --------------------------------------------------------------------------------------------------
# Sizing (mirrors references/exposure-and-limits.md)
# --------------------------------------------------------------------------------------------------
def cap_weights(w, cap):
    w = dict(w)
    for _ in range(100):
        over = [k for k in w if w[k] > cap + 1e-9]
        if not over:
            break
        excess = sum(w[k] - cap for k in over)
        for k in over:
            w[k] = cap
        under = [k for k in w if w[k] < cap - 1e-12]
        tot = sum(w[k] for k in under)
        if tot <= 0:
            break
        for k in under:
            w[k] += excess * (w[k] / tot)
    return w


def correlation_clusters(assets, ret_window, threshold):
    parent = {a: a for a in assets}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(assets)):
        for j in range(i + 1, len(assets)):
            if pearson(ret_window[assets[i]], ret_window[assets[j]]) > threshold:
                parent[find(assets[i])] = find(assets[j])
    clusters = {}
    for a in assets:
        clusters.setdefault(find(a), []).append(a)
    return list(clusters.values())


def target_weights(universe, ret_hist, prices, t, sizing, corr_cfg):
    """Return weights over `universe` (0 for excluded assets). Sleeve sums to 1 unless fully filtered out."""
    zeros = {a: 0.0 for a in universe}

    # asset-level trend filter (dual-momentum lite): only hold assets above their own MA
    tf = sizing.get("trend_filter", {}) or {}
    assets = list(universe)
    if tf.get("enabled"):
        ma_days = tf.get("ma_days", 50)
        assets = [a for a in universe if t > ma_days and prices[a][t - 1] > sma(prices[a], t, ma_days)]
    if not assets:
        return zeros, {}

    vlb = sizing["vol_lookback_days"]
    vols = {a: max(stdev(ret_hist[a][max(0, t - vlb):t]) * math.sqrt(ANN), 1e-6) for a in assets}
    if sizing["method"] == "equal_weight":
        w = {a: 1.0 / len(assets) for a in assets}
    else:
        raw = {a: 1.0 / vols[a] for a in assets}
        tot = sum(raw.values())
        w = {a: raw[a] / tot for a in assets}

    w = cap_weights(w, sizing["max_weight_per_asset"])

    if corr_cfg["penalty"] != "none" and len(assets) > 1:
        clb = corr_cfg["lookback_days"]
        ret_window = {a: ret_hist[a][max(0, t - clb):t] for a in assets}
        for cluster in correlation_clusters(assets, ret_window, corr_cfg["max_pairwise"]):
            if len(cluster) > 1:
                factor = 1.0 / math.sqrt(len(cluster))
                for a in cluster:
                    w[a] *= factor
        tot = sum(w.values())
        if tot > 0:
            w = {a: w[a] / tot for a in assets}
        w = cap_weights(w, sizing["max_weight_per_asset"])

    out = dict(zeros)
    out.update(w)
    return out, vols


# --------------------------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------------------------
def equity_metrics(equity):
    rets = [equity[i] / equity[i - 1] - 1.0 for i in range(1, len(equity)) if equity[i - 1] > 0]
    n = len(equity) - 1
    total = equity[-1] / equity[0] - 1.0
    cagr = (equity[-1] / equity[0]) ** (ANN / n) - 1.0 if n > 0 and equity[0] > 0 else 0.0
    vol = stdev(rets) * math.sqrt(ANN)
    sharpe = (mean(rets) * ANN / vol) if vol > 0 and rets else 0.0
    peak, maxdd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        maxdd = max(maxdd, (peak - e) / peak if peak > 0 else 0.0)
    calmar = (cagr / maxdd) if maxdd > 0 else float("inf")
    return {"total_return": total, "cagr": cagr, "vol": vol, "sharpe": sharpe,
            "max_drawdown": maxdd, "calmar": calmar}


# --------------------------------------------------------------------------------------------------
# Backtest engines
# --------------------------------------------------------------------------------------------------
def run_baseline(universe, prices, cap):
    n = len(prices[universe[0]])
    w0 = 1.0 / len(universe)
    units = {a: (cap * w0) / prices[a][0] for a in universe}
    return [sum(units[a] * prices[a][t] for a in universe) for t in range(n)]


def run_overlay(universe, prices, fng, funding, oi, spec, exposure_override=None):
    """If exposure_override is given (list aligned to days, value in [0,1]), it replaces the rule-based
    regime budget while ALL other machinery (trend filter, vol targeting, drawdown control, smoothing)
    stays identical -- a fair A/B between the rule regime and an external signal such as the ML classifier.
    """
    sizing = merged(spec, "sizing")
    corr_cfg = merged(spec, "correlation")
    limits = merged(spec, "limits")
    dd = merged(spec, "drawdown_control")
    reb = merged(spec, "rebalance")
    execu = merged(spec, "execution")
    exposure_by_regime = merged(spec, "regime")["exposure_by_regime"]
    cap0 = spec.get("base_capital_usd", DEFAULTS["base_capital_usd"])

    n = len(prices[universe[0]])
    ret_hist = {a: [0.0] + [prices[a][t] / prices[a][t - 1] - 1.0 for t in range(1, n)] for a in universe}
    index_hist = []
    base = {a: prices[a][0] for a in universe}

    warmup = max(sizing["vol_lookback_days"], corr_cfg["lookback_days"],
                 (sizing.get("trend_filter") or {}).get("ma_days", 0)) + 1
    throttle = sorted(dd["throttle"], key=lambda x: x["dd_gte"])
    span = max(1, execu.get("exposure_smoothing_span_days", 1))
    alpha = 2.0 / (span + 1.0)
    smooth_mode = execu.get("smoothing_mode", "none")

    equity = [cap0]
    hwm = cap0
    cur_w = {a: 0.0 for a in universe}
    killed = False
    cooldown = 0
    prev_gross = 0.0
    regimes, gross_series = [], []

    for t in range(1, n):
        index_hist.append(sum(prices[a][t - 1] / base[a] for a in universe) / len(universe))
        if t < warmup:
            equity.append(equity[-1])
            regimes.append("warmup")
            gross_series.append(0.0)
            continue

        if (t - warmup) % reb["frequency_days"] == 0 or sum(abs(v) for v in cur_w.values()) == 0:
            cur_w, _ = target_weights(universe, ret_hist, prices, t, sizing, corr_cfg)
        sleeve_invested = sum(cur_w.values()) > 1e-9

        if exposure_override is not None:
            reg, regime_mult = "ml", exposure_override[t]
        else:
            reg, _ = regime_label(fng[t - 1], funding[t - 1], oi[t - 1], index_hist)
            regime_mult = exposure_by_regime.get(reg, 0.65)

        sleeve_window = [sum(cur_w[a] * ret_hist[a][d] for a in universe)
                         for d in range(max(1, t - sizing["vol_lookback_days"]), t)]
        realized = stdev(sleeve_window) * math.sqrt(ANN) if len(sleeve_window) > 1 else 0.0
        vol_scalar = (sizing["max_vol_scalar"] if realized <= 0
                      else min(sizing["max_vol_scalar"], sizing["target_portfolio_vol_annual"] / realized))

        cur_dd = (hwm - equity[-1]) / hwm if hwm > 0 else 0.0
        throttle_mult = 1.0
        for rule in throttle:
            if cur_dd >= rule["dd_gte"]:
                throttle_mult = rule["exposure_mult"]

        if killed:
            cooldown -= 1
            if cooldown <= 0:
                killed = False
                hwm = equity[-1]
        elif cur_dd >= dd["kill_switch_dd"]:
            killed = True
            cooldown = dd["reentry"]["cooldown_days"]

        raw_gross = 0.0 if (killed or not sleeve_invested) else \
            min(limits["max_gross_exposure"], regime_mult * vol_scalar) * throttle_mult

        # exposure smoothing: cut instantly, re-risk gradually (reduces whipsaw without delaying protection)
        if smooth_mode == "asymmetric_fast_down":
            gross = raw_gross if raw_gross < prev_gross else alpha * raw_gross + (1 - alpha) * prev_gross
        elif smooth_mode == "symmetric":
            gross = alpha * raw_gross + (1 - alpha) * prev_gross
        else:
            gross = raw_gross
        prev_gross = gross

        sleeve_ret = sum(cur_w[a] * ret_hist[a][t] for a in universe)
        new_eq = equity[-1] * (1.0 + gross * sleeve_ret)
        equity.append(new_eq)
        if not killed:
            hwm = max(hwm, new_eq)
        regimes.append(reg)
        gross_series.append(gross)

    tim = sum(1 for g in gross_series if g > 1e-6) / len(gross_series) if gross_series else 0.0
    counts = {}
    for r in regimes:
        counts[r] = counts.get(r, 0) + 1
    return equity, tim, counts


# --------------------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------------------
def pct(x):
    return f"{x * 100:,.1f}%"


def fmt_calmar(c):
    return "inf" if c == float("inf") else f"{c:.2f}"


def print_report(spec, base_m, ovl_m, tim, counts, dates):
    line = "-" * 64
    print()
    print("=" * 64)
    print(f"  PORTFOLIO RISK BACKTEST  |  {spec.get('name', 'unnamed spec')}")
    print("=" * 64)
    print(f"  Universe : {', '.join(spec['universe'])}")
    print(f"  Period   : {dates[0]} -> {dates[-1]}  ({len(dates)} days)")
    print(f"  Capital  : ${spec.get('base_capital_usd', 10000):,.0f}")
    print(line)
    print(f"  {'Metric':<22}{'Buy&Hold (EW)':>18}{'Risk Overlay':>18}")
    print(line)
    rows = [
        ("Total return", pct(base_m["total_return"]), pct(ovl_m["total_return"])),
        ("CAGR", pct(base_m["cagr"]), pct(ovl_m["cagr"])),
        ("Annualized vol", pct(base_m["vol"]), pct(ovl_m["vol"])),
        ("Sharpe", f"{base_m['sharpe']:.2f}", f"{ovl_m['sharpe']:.2f}"),
        ("Max drawdown", pct(base_m["max_drawdown"]), pct(ovl_m["max_drawdown"])),
        ("Calmar (CAGR/MDD)", fmt_calmar(base_m["calmar"]), fmt_calmar(ovl_m["calmar"])),
        ("Time in market", "100.0%", pct(tim)),
    ]
    for name, b, o in rows:
        print(f"  {name:<22}{b:>18}{o:>18}")
    print(line)
    print("  Days per regime (overlay): " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(line)
    print(f"  Sharpe {base_m['sharpe']:.2f} -> {ovl_m['sharpe']:.2f}  |  "
          f"Max DD {pct(base_m['max_drawdown'])} -> {pct(ovl_m['max_drawdown'])}  |  "
          f"Calmar {fmt_calmar(base_m['calmar'])} -> {fmt_calmar(ovl_m['calmar'])}")
    print("=" * 64)
    print()


def run_monte_carlo(spec, n_paths):
    universe = spec["universe"]
    cap = spec.get("base_capital_usd", 10000)
    bs, os_, bdd, odd, bc, oc, wins = [], [], [], [], [], [], 0
    for seed in range(1, n_paths + 1):
        _, prices, fng, funding, oi = build_synthetic(universe, seed=seed, jitter=True)
        base_m = equity_metrics(run_baseline(universe, prices, cap))
        ovl_eq, _, _ = run_overlay(universe, prices, fng, funding, oi, spec)
        ovl_m = equity_metrics(ovl_eq)
        bs.append(base_m["sharpe"]); os_.append(ovl_m["sharpe"])
        bdd.append(base_m["max_drawdown"]); odd.append(ovl_m["max_drawdown"])
        bc.append(base_m["calmar"] if base_m["calmar"] != float("inf") else 0)
        oc.append(ovl_m["calmar"] if ovl_m["calmar"] != float("inf") else 0)
        if ovl_m["sharpe"] > base_m["sharpe"]:
            wins += 1
    line = "-" * 64
    print()
    print("=" * 64)
    print(f"  MONTE CARLO ROBUSTNESS  |  {n_paths} synthetic paths  |  {spec.get('name','')}")
    print("=" * 64)
    print(f"  {'Metric (mean / median)':<26}{'Buy&Hold':>17}{'Overlay':>17}")
    print(line)
    print(f"  {'Sharpe':<26}{mean(bs):>8.2f} /{median(bs):>6.2f}{mean(os_):>9.2f} /{median(os_):>6.2f}")
    print(f"  {'Max drawdown':<26}{pct(mean(bdd)):>17}{pct(mean(odd)):>17}")
    print(f"  {'Calmar':<26}{mean(bc):>17.2f}{mean(oc):>17.2f}")
    print(line)
    print(f"  Overlay beat Buy&Hold on Sharpe in {wins}/{n_paths} paths ({100*wins/n_paths:.0f}%).")
    print(f"  Mean Sharpe uplift: +{mean(os_) - mean(bs):.2f}   "
          f"Mean drawdown cut: {pct(mean(bdd) - mean(odd))}")
    print("=" * 64)
    print()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Backtest a portfolio_risk_spec.json")
    ap.add_argument("--spec", default=os.path.join(here, "..", "examples", "sample_risk_spec.json"))
    ap.add_argument("--data", default=None, help="CSV of prices + regime columns. Synthetic if omitted.")
    ap.add_argument("--out", default=None, help="Optional path to write the two equity curves as CSV.")
    ap.add_argument("--mc", type=int, default=0, help="Run Monte Carlo over N synthetic paths instead.")
    args = ap.parse_args()

    with open(args.spec) as f:
        spec = json.load(f)
    universe = spec["universe"]

    if args.mc > 0:
        run_monte_carlo(spec, args.mc)
        return

    if args.data:
        dates, prices, fng, funding, oi = load_data(args.data, universe)
    else:
        dates, prices, fng, funding, oi = build_synthetic(universe, seed=42)
        csv_path = os.path.join(here, "data", "prices_sample.csv")
        write_csv(csv_path, dates, prices, fng, funding, oi, universe)
        print(f"[info] wrote synthetic dataset -> {os.path.relpath(csv_path, here)}")

    base_eq = run_baseline(universe, prices, spec.get("base_capital_usd", 10000))
    ovl_eq, tim, counts = run_overlay(universe, prices, fng, funding, oi, spec)
    print_report(spec, equity_metrics(base_eq), equity_metrics(ovl_eq), tim, counts, dates)

    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "buy_hold_equity", "overlay_equity"])
            for i, d in enumerate(dates):
                w.writerow([d, round(base_eq[i], 2), round(ovl_eq[i], 2)])
        print(f"[info] wrote equity curves -> {args.out}")


if __name__ == "__main__":
    main()
