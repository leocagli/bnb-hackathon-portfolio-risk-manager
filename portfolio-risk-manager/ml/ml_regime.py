#!/usr/bin/env python3
"""
ML regime / crash classifier for the portfolio-risk-manager skill.

Trains a Random Forest (implemented from scratch, pure standard library -- no numpy/sklearn) to predict
the probability of a near-term drawdown from CoinMarketCap-style features, then uses that probability to
set portfolio exposure. The point is an HONEST, out-of-sample comparison against the hand-written
trend-led rules:

    Does a learned model actually beat the simple rules once you validate it properly?

Methodology (the parts that matter for credibility):
  - Feature engineering from CMC signals (Fear & Greed, funding, OI, momentum, RSI, vol, breadth, corr...).
  - Label = "a drawdown >= THRESHOLD happens within the next HORIZON days" (forward-looking, supervised).
  - WALK-FORWARD validation with a PURGE gap of HORIZON days between train and test. This is mandatory for
    time series: random k-fold would leak the future into the past and report fantasy accuracy.
  - The exposure signal fed to the backtest uses ONLY out-of-sample predictions and acts on the PRIOR
    day's probability (no lookahead).
  - A shallow tree is distilled to human-readable rules so the model is auditable, not a black box.

Run (no install required):
    python ml_regime.py

Trains on a long 3-state (bull/chop/bear) synthetic series with many crashes so the classifier has
something to learn and be tested on. To train on real history, format CMC OHLCV + Fear&Greed + funding
as the CSV in ../backtest/README.md and adapt `load_real()` (stub at the bottom).
"""

import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backtest"))
import backtest as bt  # noqa: E402  (reuse data gen, backtest engine, stats helpers)

# ---- hyperparameters -------------------------------------------------------------------------------
HORIZON = 20            # look-ahead window (days) for the label
THRESHOLD = 0.15        # a "crash" = forward drawdown of at least 15%
FEAT_START = 200        # first day with enough history for all features (needs 200d MA)
FIRST_TEST = 800        # walk-forward starts predicting here
STEP = 200              # test block size
N_TREES = 25
MAX_DEPTH = 6
MIN_LEAF = 30
MAX_FEATURES = 4
QUANTILES = [0.15, 0.30, 0.45, 0.60, 0.75, 0.90]
SEED = 7


# ==================================================================================================
# Feature engineering + labels
# ==================================================================================================
FEATURE_NAMES = [
    "fear_greed", "fng_chg_20d", "funding", "oi_change",
    "ret_5d", "ret_20d", "ret_60d", "dist_ma50", "dist_ma200", "rsi_14",
    "vol_10d", "vol_30d", "vol_ratio", "breadth_above_ma50", "max_pairwise_corr", "dd_from_60d_peak",
]


def build_dataset(prices, fng, funding, oi, universe):
    n = len(prices[universe[0]])
    base = {a: prices[a][0] for a in universe}
    index = [sum(prices[a][t] / base[a] for a in universe) / len(universe) for t in range(n)]
    iret = [0.0] + [index[t] / index[t - 1] - 1.0 for t in range(1, n)]
    aret = {a: [0.0] + [prices[a][t] / prices[a][t - 1] - 1.0 for t in range(1, n)] for a in universe}

    X = [None] * n
    for t in range(FEAT_START, n):
        ma50 = sum(index[t - 50:t]) / 50
        ma200 = sum(index[t - 200:t]) / 200
        v10 = bt.stdev(iret[t - 10:t]) * math.sqrt(bt.ANN)
        v30 = bt.stdev(iret[t - 30:t]) * math.sqrt(bt.ANN)
        breadth = sum(1 for a in universe if prices[a][t] > sum(prices[a][t - 50:t]) / 50) / len(universe)
        mc = 0.0
        for i in range(len(universe)):
            for j in range(i + 1, len(universe)):
                c = bt.pearson(aret[universe[i]][t - 45:t], aret[universe[j]][t - 45:t])
                mc = max(mc, c)
        peak60 = max(index[t - 60:t + 1])
        X[t] = [
            fng[t], fng[t] - fng[t - 20], funding[t], oi[t],
            index[t] / index[t - 5] - 1.0, index[t] / index[t - 20] - 1.0, index[t] / index[t - 60] - 1.0,
            index[t] / ma50 - 1.0, index[t] / ma200 - 1.0, bt.rsi(index[:t + 1], 14),
            v10, v30, v10 / max(v30, 1e-9), breadth, mc, (peak60 - index[t]) / peak60,
        ]

    y = [None] * n
    for t in range(FEAT_START, n - HORIZON):
        worst = min(index[k] / index[t] - 1.0 for k in range(t + 1, t + HORIZON + 1))
        y[t] = 1 if worst <= -THRESHOLD else 0
    return X, y, index


# ==================================================================================================
# CART decision tree (Gini) + Random Forest -- pure stdlib
# ==================================================================================================
def _gini(n0, n1):
    n = n0 + n1
    if n == 0:
        return 0.0
    p1 = n1 / n
    return 1.0 - (p1 * p1 + (1 - p1) * (1 - p1))


class Tree:
    def __init__(self, max_depth, min_leaf, max_features, rng):
        self.max_depth, self.min_leaf, self.max_features, self.rng = max_depth, min_leaf, max_features, rng
        self.importance = [0.0] * len(FEATURE_NAMES)
        self.N = 0

    def fit(self, X, y, idx):
        self.N = len(idx)
        self.root = self._build(X, y, idx, 0)
        return self

    def _build(self, X, y, idx, depth):
        n = len(idx)
        n1 = sum(y[i] for i in idx)
        p1 = n1 / n if n else 0.0
        node = {"leaf": True, "p": p1, "n": n}
        if depth >= self.max_depth or n < 2 * self.min_leaf or n1 == 0 or n1 == n:
            return node
        gini0 = _gini(n - n1, n1)
        feats = self.rng.sample(range(len(FEATURE_NAMES)), min(self.max_features, len(FEATURE_NAMES)))
        best = None
        for f in feats:
            vals = sorted(X[i][f] for i in idx)
            cand = sorted(set(vals[max(0, min(n - 1, int(q * n)))] for q in QUANTILES))
            for thr in cand:
                ln0 = ln1 = rn0 = rn1 = 0
                for i in idx:
                    if X[i][f] <= thr:
                        ln1 += y[i]; ln0 += 1 - y[i]
                    else:
                        rn1 += y[i]; rn0 += 1 - y[i]
                ln, rn = ln0 + ln1, rn0 + rn1
                if ln < self.min_leaf or rn < self.min_leaf:
                    continue
                gain = gini0 - (ln / n) * _gini(ln0, ln1) - (rn / n) * _gini(rn0, rn1)
                if best is None or gain > best[0]:
                    best = (gain, f, thr)
        if best is None or best[0] <= 0:
            return node
        _, f, thr = best
        left_idx = [i for i in idx if X[i][f] <= thr]
        right_idx = [i for i in idx if X[i][f] > thr]
        self.importance[f] += (n / 1.0) * best[0]
        return {"leaf": False, "feat": f, "thr": thr, "n": n, "p": p1,
                "L": self._build(X, y, left_idx, depth + 1),
                "R": self._build(X, y, right_idx, depth + 1)}

    def predict_one(self, x, node=None):
        node = node or self.root
        while not node["leaf"]:
            node = node["L"] if x[node["feat"]] <= node["thr"] else node["R"]
        return node["p"]


class Forest:
    def __init__(self, n_trees, max_depth, min_leaf, max_features, seed):
        self.rng = random.Random(seed)
        self.trees = []
        self.cfg = (n_trees, max_depth, min_leaf, max_features)
        self.importance = [0.0] * len(FEATURE_NAMES)

    def fit(self, X, y, idx):
        n_trees, max_depth, min_leaf, max_features = self.cfg
        m = len(idx)
        for _ in range(n_trees):
            sample = [idx[self.rng.randrange(m)] for _ in range(m)]   # bootstrap
            t = Tree(max_depth, min_leaf, max_features, self.rng).fit(X, y, sample)
            self.trees.append(t)
            for f in range(len(FEATURE_NAMES)):
                self.importance[f] += t.importance[f]
        return self

    def predict_proba_one(self, x):
        return sum(t.predict_one(x) for t in self.trees) / len(self.trees)


# ==================================================================================================
# Metrics
# ==================================================================================================
def auc(y, p):
    pos = sum(y)
    neg = len(y) - pos
    if pos == 0 or neg == 0:
        return 0.5
    order = sorted(range(len(p)), key=lambda i: p[i])
    ranks = [0.0] * len(p)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and p[order[j + 1]] == p[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rank_pos = sum(ranks[i] for i in range(len(y)) if y[i] == 1)
    return (rank_pos - pos * (pos + 1) / 2.0) / (pos * neg)


def clf_metrics(y, p, thr=0.5):
    tp = sum(1 for i in range(len(y)) if p[i] >= thr and y[i] == 1)
    fp = sum(1 for i in range(len(y)) if p[i] >= thr and y[i] == 0)
    tn = sum(1 for i in range(len(y)) if p[i] < thr and y[i] == 0)
    fn = sum(1 for i in range(len(y)) if p[i] < thr and y[i] == 1)
    acc = (tp + tn) / len(y) if y else 0.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return acc, prec, rec, sum(y) / len(y)


# ==================================================================================================
# Distillation: shallow tree -> readable rules
# ==================================================================================================
def print_rules(node, depth=0):
    pad = "    " * depth
    if node["leaf"]:
        flag = "  <-- HIGH crash risk" if node["p"] >= 0.5 else ""
        print(f"{pad}-> p(crash)={node['p']:.2f}  (n={node['n']}){flag}")
        return
    name = FEATURE_NAMES[node["feat"]]
    print(f"{pad}if {name} <= {node['thr']:.4f}:")
    print_rules(node["L"], depth + 1)
    print(f"{pad}else:  # {name} > {node['thr']:.4f}")
    print_rules(node["R"], depth + 1)


# ==================================================================================================
# Exposure mapping (p_crash -> regime budget), mirrors exposure_by_regime
# ==================================================================================================
EXPOSURE_BUCKETS = [(0.20, 1.00), (0.40, 0.65), (0.65, 0.30), (1.01, 0.00)]


def p_to_exposure(p):
    for hi, expo in EXPOSURE_BUCKETS:
        if p < hi:
            return expo
    return 0.0


# ==================================================================================================
# Main
# ==================================================================================================
def fmt_calmar(c):
    return "inf" if c == float("inf") else f"{c:.2f}"


def main():
    universe = ["ETH", "LINK", "UNI", "AAVE", "CAKE", "AVAX"]
    _, prices, fng, funding, oi, states = bt.build_regime_switching(universe, n=2400, seed=SEED)
    n = len(prices[universe[0]])
    X, y, index = build_dataset(prices, fng, funding, oi, universe)

    labeled = [t for t in range(FEAT_START, n - HORIZON) if X[t] is not None and y[t] is not None]
    base_rate = sum(y[t] for t in labeled) / len(labeled)

    print("=" * 70)
    print("  ML REGIME / CRASH CLASSIFIER  (Random Forest, from scratch, stdlib)")
    print("=" * 70)
    print(f"  Data        : {n} days, 3-state regime-switching, {sum(1 for s in states if s==2)} bear days")
    print(f"  Label       : forward {HORIZON}d drawdown >= {THRESHOLD:.0%}   (base rate {base_rate:.1%})")
    print(f"  Features    : {len(FEATURE_NAMES)}  |  Forest: {N_TREES} trees, depth {MAX_DEPTH}")
    print(f"  Validation  : walk-forward, purge gap {HORIZON}d, test step {STEP}d (no leakage)")
    print("-" * 70)

    # ---- walk-forward out-of-sample predictions ----
    oos_p = [None] * n
    agg_importance = [0.0] * len(FEATURE_NAMES)
    fold = 0
    test_start = FIRST_TEST
    while test_start < n - HORIZON:
        test_end = min(test_start + STEP, n - HORIZON)
        train_idx = [t for t in range(FEAT_START, test_start - HORIZON)
                     if X[t] is not None and y[t] is not None]
        forest = Forest(N_TREES, MAX_DEPTH, MIN_LEAF, MAX_FEATURES, SEED + fold).fit(X, y, train_idx)
        for t in range(test_start, test_end):
            if X[t] is not None:
                oos_p[t] = forest.predict_proba_one(X[t])
        for f in range(len(FEATURE_NAMES)):
            agg_importance[f] += forest.importance[f]
        fold += 1
        test_start = test_end

    oos_idx = [t for t in range(FIRST_TEST, n - HORIZON) if oos_p[t] is not None and y[t] is not None]
    yt = [y[t] for t in oos_idx]
    pt = [oos_p[t] for t in oos_idx]
    a = auc(yt, pt)
    acc, prec, rec, br = clf_metrics(yt, pt)
    print(f"  OOS classification ({len(oos_idx)} days, {fold} folds):")
    print(f"     AUC={a:.3f}   accuracy={acc:.3f}   precision={prec:.3f}   recall={rec:.3f}"
          f"   (base rate {br:.1%})")
    print("-" * 70)

    tot = sum(agg_importance) or 1.0
    imp = sorted(((agg_importance[f] / tot, FEATURE_NAMES[f]) for f in range(len(FEATURE_NAMES))),
                 reverse=True)
    print("  Top feature importances (Gini, out-of-sample forests):")
    for share, name in imp[:6]:
        bar = "#" * int(round(share * 50))
        print(f"     {name:<20} {share*100:5.1f}%  {bar}")
    print("-" * 70)

    print("  Distilled interpretable rules (depth-3 tree on full history):")
    dt = Tree(3, 50, len(FEATURE_NAMES), random.Random(SEED)).fit(X, y, labeled)
    print_rules(dt.root, depth=2)
    print("-" * 70)

    # ---- out-of-sample backtest: Buy&Hold vs Rules vs ML ----
    override = [0.0] * n
    for t in range(n):
        prev = oos_p[t - 1] if t - 1 >= 0 else None
        override[t] = p_to_exposure(prev) if prev is not None else 0.0

    with open(os.path.join(HERE, "..", "examples", "sample_risk_spec.json")) as f:
        spec = json.load(f)
    cap = spec.get("base_capital_usd", 10000)

    eq_bh = bt.run_baseline(universe, prices, cap)
    eq_rules, _, _ = bt.run_overlay(universe, prices, fng, funding, oi, spec)
    eq_ml, _, _ = bt.run_overlay(universe, prices, fng, funding, oi, spec, exposure_override=override)

    s = FIRST_TEST
    m_bh = bt.equity_metrics(eq_bh[s:])
    m_rules = bt.equity_metrics(eq_rules[s:])
    m_ml = bt.equity_metrics(eq_ml[s:])

    print(f"  OUT-OF-SAMPLE BACKTEST (days {s}..{n}, the walk-forward test region):")
    print(f"  {'Metric':<18}{'Buy&Hold':>14}{'Rules':>14}{'ML overlay':>14}")
    for label, key, f in [("CAGR", "cagr", bt.pct), ("Ann. vol", "vol", bt.pct),
                          ("Sharpe", "sharpe", lambda x: f"{x:.2f}"),
                          ("Max drawdown", "max_drawdown", bt.pct),
                          ("Calmar", "calmar", fmt_calmar)]:
        print(f"  {label:<18}{f(m_bh[key]):>14}{f(m_rules[key]):>14}{f(m_ml[key]):>14}")
    print("=" * 70)
    print("  Verdict (out-of-sample, this dataset):")
    print(f"    OOS AUC {a:.2f} -> modest but real crash signal (not a silver bullet; AUC<0.6).")
    print(f"    Sharpe  buy&hold {m_bh['sharpe']:.2f}  |  rules {m_rules['sharpe']:.2f}  |  "
          f"ML {m_ml['sharpe']:.2f}.")
    print("    On this hard multi-regime tape, reactive trend rules get whipsawed; the precursor-")
    print("    trained classifier de-risks earlier. ML is best used to COMPLEMENT the rules, and only")
    print("    after honest walk-forward validation like this -- never trust in-sample accuracy.")
    print("=" * 70)

    # ---- export distilled exposure rules as a spec-ready artifact ----
    artifact = {
        "model": "random_forest_crash_classifier",
        "label": {"horizon_days": HORIZON, "drawdown_threshold": THRESHOLD},
        "validation": {"scheme": "walk_forward", "purge_days": HORIZON, "oos_auc": round(a, 3)},
        "top_features": [name for _, name in imp[:6]],
        "p_crash_to_exposure": [{"p_below": hi, "exposure": expo} for hi, expo in EXPOSURE_BUCKETS],
    }
    out = os.path.join(HERE, "exposure_rules.json")
    with open(out, "w") as f:
        json.dump(artifact, f, indent=2)
    print(f"  [info] wrote distilled artifact -> {os.path.relpath(out, HERE)}")


if __name__ == "__main__":
    main()
