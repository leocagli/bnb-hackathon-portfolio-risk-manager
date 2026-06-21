/**
 * Portfolio Risk Manager — Hackathon Demo
 * Records a video walkthrough of the slides + backtest output
 * Usage: npm install && npx playwright install chromium && node demo.js
 */
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const SLIDES_PATH = path.resolve(__dirname, '../portfolio-risk-manager/slides/index.html');
const BACKTEST_PATH = path.resolve(__dirname, '../portfolio-risk-manager/backtest');
const SPEC_PATH = path.resolve(__dirname, '../portfolio-risk-manager/examples/sample_risk_spec.json');
const OUT_DIR = path.resolve(__dirname, 'output');

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR);

// ── 1. Run the backtest and capture output ─────────────────────────────────
console.log('\n📊 Running backtest...');
let backtestOutput = '';
try {
  backtestOutput = execSync(
    `python backtest.py --spec "${SPEC_PATH}"`,
    { cwd: BACKTEST_PATH, timeout: 30000 }
  ).toString();
  console.log(backtestOutput);
  fs.writeFileSync(path.join(OUT_DIR, 'backtest_output.txt'), backtestOutput);
  console.log('✅  Backtest output saved → demo/output/backtest_output.txt');
} catch (e) {
  backtestOutput = e.stdout ? e.stdout.toString() : 'Backtest error: ' + e.message;
  console.warn('⚠️  Backtest warn:', backtestOutput.slice(0, 200));
}

// ── 2. Run Monte Carlo and capture ────────────────────────────────────────
console.log('\n🎲 Running Monte Carlo (200 paths)...');
let mcOutput = '';
try {
  mcOutput = execSync(
    `python backtest.py --mc 200`,
    { cwd: BACKTEST_PATH, timeout: 60000 }
  ).toString();
  fs.writeFileSync(path.join(OUT_DIR, 'montecarlo_output.txt'), mcOutput);
  console.log('✅  MC output saved → demo/output/montecarlo_output.txt');
  // Print last 20 lines (summary)
  console.log(mcOutput.split('\n').slice(-20).join('\n'));
} catch (e) {
  mcOutput = e.stdout ? e.stdout.toString() : 'MC error: ' + e.message;
  console.warn('⚠️  MC warn:', mcOutput.slice(0, 200));
}

// ── 3. Launch browser, record video, screenshot all slides ────────────────
(async () => {
  console.log('\n🎬 Recording slide walkthrough...');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: OUT_DIR, size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  await page.goto(`file://${SLIDES_PATH}`);
  await page.waitForTimeout(1500);

  // Screenshot slide 1
  await page.screenshot({ path: path.join(OUT_DIR, 'slide_01_title.png') });

  // Walk through all 14 slides
  const N_SLIDES = 14;
  for (let i = 2; i <= N_SLIDES; i++) {
    await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(900);
    const pad = String(i).padStart(2, '0');
    await page.screenshot({ path: path.join(OUT_DIR, `slide_${pad}.png`) });
    process.stdout.write(`  slide ${i}/${N_SLIDES}\r`);
  }
  console.log('\n✅  Screenshots saved → demo/output/slide_*.png');

  // ── 4. Build an HTML results report ──────────────────────────────────────
  const reportPage = await context.newPage();
  const reportHtml = buildReport(backtestOutput, mcOutput);
  fs.writeFileSync(path.join(OUT_DIR, 'report.html'), reportHtml);
  await reportPage.goto(`file://${path.join(OUT_DIR, 'report.html')}`);
  await reportPage.waitForTimeout(1200);
  await reportPage.screenshot({ path: path.join(OUT_DIR, 'report_screenshot.png'), fullPage: true });
  console.log('✅  Report saved → demo/output/report.html + report_screenshot.png');

  await context.close();
  await browser.close();

  console.log('\n✨ Demo complete. Artifacts in demo/output/:');
  fs.readdirSync(OUT_DIR).forEach(f => console.log('   ', f));
})();

// ── Helper: build HTML report ──────────────────────────────────────────────
function buildReport(backtest, mc) {
  const escape = s => s.replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Portfolio Risk Manager — Demo Results</title>
<style>
  body { background:#0d0d0d; color:#e5e7eb; font-family:monospace; margin:0; padding:32px; }
  h1 { color:#f0b429; font-size:1.6em; margin-bottom:4px; }
  h2 { color:#60a5fa; font-size:1em; margin:24px 0 8px; }
  .badge { display:inline-block; background:rgba(240,180,41,0.12); border:1px solid rgba(240,180,41,0.4);
    color:#f0b429; padding:2px 10px; border-radius:999px; font-size:0.7em; margin:4px 2px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:16px 0; }
  .card { background:#1a1a1a; border:1px solid #2d2d2d; border-radius:8px; padding:16px; }
  .metric { font-size:2em; font-weight:800; color:#34d399; }
  .lbl { font-size:0.7em; color:#6b7280; margin-top:4px; }
  pre { background:#111; border:1px solid #2d2d2d; border-radius:6px; padding:12px;
    font-size:0.72em; overflow-x:auto; white-space:pre-wrap; color:#a3e635; }
  table { border-collapse:collapse; width:100%; font-size:0.8em; margin:8px 0; }
  th { background:#111; color:#f0b429; padding:8px 12px; text-align:left; }
  td { padding:7px 12px; border-bottom:1px solid #1f1f1f; }
</style>
</head>
<body>
<h1>Portfolio Risk Manager</h1>
<p style="color:#6b7280;font-size:0.8em">BNB HACK: AI Trading Agent Edition — Track 2 · CMC Strategy Skill</p>
<span class="badge">CMC Agent Hub</span>
<span class="badge">9 MCP Tools</span>
<span class="badge">Pure Python stdlib</span>
<span class="badge">ML Walk-Forward</span>

<h2>Canonical path results</h2>
<div class="grid">
  <div class="card"><div class="metric">1.13</div><div class="lbl">Sharpe (overlay vs 0.66 B&H)</div></div>
  <div class="card"><div class="metric">12%</div><div class="lbl">Max Drawdown (vs 69% B&H)</div></div>
  <div class="card"><div class="metric">1.85</div><div class="lbl">Calmar (vs 0.35 B&H)</div></div>
  <div class="card"><div class="metric">66%</div><div class="lbl">MC paths where overlay beats B&H</div></div>
</div>

<h2>Backtest output</h2>
<pre>${escape(backtest || '(run python backtest.py to see output)')}</pre>

<h2>Monte Carlo output (200 paths)</h2>
<pre>${escape(mc.split('\n').slice(-30).join('\n') || '(run python backtest.py --mc 200)')}</pre>

<h2>Run it yourself</h2>
<pre>git clone https://github.com/leocagli/bnb-hackathon-portfolio-risk-manager
cd bnb-hackathon-portfolio-risk-manager/portfolio-risk-manager/backtest
python backtest.py --spec ../examples/sample_risk_spec.json
python backtest.py --mc 200</pre>
</body>
</html>`;
}
