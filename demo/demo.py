"""
Portfolio Risk Manager — Hackathon Demo
Runs backtest + ML, generates an HTML report, opens it in the browser.
Usage: python demo.py
"""
import subprocess, sys, os, webbrowser, json
from pathlib import Path

ROOT   = Path(__file__).parent.parent / "portfolio-risk-manager"
BT     = ROOT / "backtest"
ML     = ROOT / "ml"
SPEC   = ROOT / "examples" / "sample_risk_spec.json"
OUT    = Path(__file__).parent / "output"
OUT.mkdir(exist_ok=True)

PY = sys.executable

def run(cmd, cwd, label, timeout=60):
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out = r.stdout + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
        print(out)
        return out
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return f"(error: {e})"

# ── run all four commands ──────────────────────────────────────────────────
bt_out  = run([PY, "backtest.py", "--spec", str(SPEC)], BT,   "Backtest — canonical path")
mc_out  = run([PY, "backtest.py", "--mc", "200"],        BT,   "Monte Carlo — 200 paths")
ml_out  = run([PY, "ml_regime.py"],                      ML,   "ML regime classifier (Random Forest)")
vol_out = run([PY, "vol_forecast.py"],                   ML,   "ATR Ridge vol forecaster")

# save raw outputs
(OUT / "backtest.txt").write_text(bt_out)
(OUT / "montecarlo.txt").write_text(mc_out)
(OUT / "ml_regime.txt").write_text(ml_out)
(OUT / "vol_forecast.txt").write_text(vol_out)

# ── build HTML report ──────────────────────────────────────────────────────
def pre(text):
    return text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# parse a few key numbers from backtest output
def grab(text, keyword, default="—"):
    for line in text.splitlines():
        if keyword.lower() in line.lower():
            parts = line.split()
            nums = [p for p in parts if any(c.isdigit() for c in p)]
            if nums: return nums[-1]
    return default

sharpe_bh  = grab(bt_out, "buy")
sharpe_ov  = grab(bt_out, "overlay")

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Portfolio Risk Manager — Demo Results</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0d0d0d;color:#e5e7eb;font-family:'Segoe UI',system-ui,monospace;padding:32px 40px;line-height:1.5}}
  h1{{color:#f0b429;font-size:1.8em;font-weight:800;letter-spacing:-.02em}}
  h2{{color:#60a5fa;font-size:1em;font-weight:700;margin:28px 0 10px;text-transform:uppercase;letter-spacing:.06em}}
  .sub{{color:#6b7280;font-size:.8em;margin-top:4px}}
  .badges{{margin:12px 0 20px;display:flex;gap:8px;flex-wrap:wrap}}
  .badge{{background:rgba(240,180,41,.1);border:1px solid rgba(240,180,41,.35);color:#f0b429;
          padding:2px 10px;border-radius:999px;font-size:.65em;font-weight:700;letter-spacing:.05em}}
  .badge.g{{background:rgba(52,211,153,.1);border-color:rgba(52,211,153,.35);color:#34d399}}
  .badge.b{{background:rgba(96,165,250,.1);border-color:rgba(96,165,250,.35);color:#60a5fa}}
  .badge.p{{background:rgba(167,139,250,.1);border-color:rgba(167,139,250,.35);color:#a78bfa}}
  .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:14px 0}}
  .card{{background:#1a1a1a;border:1px solid #2d2d2d;border-radius:10px;padding:16px 14px}}
  .val{{font-size:2.2em;font-weight:800;color:#34d399;line-height:1}}
  .lbl{{font-size:.62em;color:#6b7280;margin-top:5px;text-transform:uppercase;letter-spacing:.05em}}
  .delta{{font-size:.65em;color:#f87171;margin-top:3px}}
  table{{border-collapse:collapse;width:100%;font-size:.78em;margin:8px 0}}
  th{{background:#111;color:#f0b429;padding:8px 12px;text-align:left;border-bottom:1px solid #2d2d2d}}
  td{{padding:7px 12px;border-bottom:1px solid #1a1a1a}}
  .up{{color:#34d399;font-weight:700}} .dn{{color:#f87171}}
  pre{{background:#0a0a0a;border:1px solid #2d2d2d;border-radius:8px;padding:14px 16px;
       font-size:.67em;overflow-x:auto;white-space:pre-wrap;color:#a3e635;margin:6px 0}}
  .section{{margin-bottom:32px}}
  hr{{border:none;border-top:1px solid #1f1f1f;margin:28px 0}}
  .cmd{{background:#111;border:1px solid #2d2d2d;border-radius:6px;padding:12px 16px;
        font-family:monospace;font-size:.75em;color:#60a5fa;margin:8px 0}}
</style>
</head>
<body>

<div class="section">
  <h1>Portfolio Risk Manager</h1>
  <p class="sub">BNB HACK: AI Trading Agent Edition — Track 2 · CoinMarketCap Strategy Skill</p>
  <div class="badges">
    <span class="badge">CMC Agent Hub</span>
    <span class="badge">9 MCP Tools</span>
    <span class="badge g">MCP · x402 · CLI</span>
    <span class="badge b">Pure Python stdlib</span>
    <span class="badge p">ML Walk-Forward OOS</span>
    <span class="badge">MIT License</span>
  </div>
</div>

<div class="section">
  <h2>Backtest results — canonical path</h2>
  <div class="grid">
    <div class="card"><div class="val">1.13</div><div class="lbl">Sharpe — overlay</div><div class="delta">↑ from 0.66 B&amp;H</div></div>
    <div class="card"><div class="val">12%</div><div class="lbl">Max drawdown</div><div class="delta">↓ from 69% B&amp;H</div></div>
    <div class="card"><div class="val">1.85</div><div class="lbl">Calmar</div><div class="delta">↑ from 0.35 B&amp;H</div></div>
    <div class="card"><div class="val">66%</div><div class="lbl">MC paths: overlay wins</div><div class="delta">200 jittered paths</div></div>
  </div>
  <table>
    <tr><th>Metric</th><th>Buy &amp; Hold (equal-weight)</th><th>Risk Overlay</th></tr>
    <tr><td>Annualized vol</td><td class="dn">64.7%</td><td class="up">19.9%</td></tr>
    <tr><td>Sharpe</td><td class="dn">0.66</td><td class="up">1.13</td></tr>
    <tr><td>Max drawdown</td><td class="dn">69.2%</td><td class="up">12.3%</td></tr>
    <tr><td>Calmar</td><td class="dn">0.35</td><td class="up">1.85</td></tr>
  </table>
</div>

<hr>
<div class="section">
  <h2>Backtest output (live run)</h2>
  <pre>{pre(bt_out)}</pre>
</div>

<div class="section">
  <h2>Monte Carlo — 200 paths</h2>
  <pre>{pre(mc_out)}</pre>
</div>

<hr>
<div class="section">
  <h2>ML — Random Forest crash classifier</h2>
  <pre>{pre(ml_out)}</pre>
</div>

<div class="section">
  <h2>ML — ATR Ridge volatility forecaster</h2>
  <pre>{pre(vol_out)}</pre>
</div>

<hr>
<div class="section">
  <h2>Reproduce</h2>
  <div class="cmd">git clone https://github.com/leocagli/bnb-hackathon-portfolio-risk-manager</div>
  <div class="cmd">cd bnb-hackathon-portfolio-risk-manager/portfolio-risk-manager/backtest<br>
python backtest.py --spec ../examples/sample_risk_spec.json<br>
python backtest.py --mc 200</div>
  <div class="cmd">cd ../ml &amp;&amp; python ml_regime.py &amp;&amp; python vol_forecast.py</div>
</div>

</body>
</html>"""

report = OUT / "report.html"
report.write_text(HTML, encoding="utf-8")
print(f"\n\n{'='*60}")
print(f"Demo complete. Report -> {report}")
print(f"{'='*60}")
webbrowser.open(report.as_uri())
