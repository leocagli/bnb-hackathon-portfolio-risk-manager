/**
 * Portfolio Risk Manager — Video Demo (enhanced)
 * Scenes: title slide → 4 Python terminal runs (animated) → summary slide
 * Usage: node record_video.js
 */
const { chromium } = require('playwright');
const { spawnSync, execSync } = require('child_process');
const path = require('path');
const fs   = require('fs');

const ROOT   = path.resolve(__dirname, '../portfolio-risk-manager');
const BT_DIR = path.join(ROOT, 'backtest');
const ML_DIR = path.join(ROOT, 'ml');
const SPEC   = path.join(ROOT, 'examples/sample_risk_spec.json');
const SLIDES = path.join(ROOT, 'slides/index.html');
const OUT    = path.resolve(__dirname, 'output');
const FRAMES = path.join(OUT, 'frames');

[OUT, FRAMES].forEach(d => fs.existsSync(d) || fs.mkdirSync(d, { recursive: true }));
// clean old frames
fs.readdirSync(FRAMES).forEach(f => fs.unlinkSync(path.join(FRAMES, f)));

const sleep = ms => new Promise(r => setTimeout(r, ms));
let fi = 0;
const framePath = () => path.join(FRAMES, `frame_${String(fi++).padStart(5,'0')}.png`);

async function shot(page) {
  const p = framePath();
  await page.screenshot({ path: p });
  return p;
}
async function hold(page, ms, fps = 24) {
  const n = Math.max(1, Math.round(ms / (1000/fps)));
  const p = await shot(page);
  for (let i = 1; i < n; i++) {
    fs.copyFileSync(p, framePath());
  }
}
async function transition(page, ms = 300, fps = 24) {
  // just hold — reveal handles fade transitions visually
  await hold(page, ms, fps);
}

// ── capture all Python outputs up front ──────────────────────────────────
function runPy(args, cwd) {
  try {
    return execSync(`python ${args}`, { cwd, timeout: 60000 }).toString();
  } catch(e) { return (e.stdout||'').toString() || String(e); }
}
console.log('Running Python scripts...');
const OUT_BT  = runPy(`backtest.py --spec "${SPEC}"`, BT_DIR);
const OUT_MC  = runPy(`backtest.py --mc 200`, BT_DIR);
const OUT_ML  = runPy(`ml_regime.py`, ML_DIR);
const OUT_VOL = runPy(`vol_forecast.py`, ML_DIR);
console.log('Done. Building video...');

// ── terminal page builder ─────────────────────────────────────────────────
function termPage(title, cmd, output, accentColor = '#34d399') {
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const colorLine = s => {
    if (/sharpe/i.test(s))                              return `<span style="color:#34d399">${esc(s)}</span>`;
    if (/drawdown|max.dd|mdd/i.test(s))                return `<span style="color:#f87171">${esc(s)}</span>`;
    if (/calmar|cagr/i.test(s))                        return `<span style="color:#60a5fa">${esc(s)}</span>`;
    if (/overlay|risk overlay|ml overlay/i.test(s))    return `<span style="color:#f0b429">${esc(s)}</span>`;
    if (/auc|feature|importan|accuracy/i.test(s))      return `<span style="color:#a78bfa">${esc(s)}</span>`;
    if (/r2|rmse|ridge|ewma|random.walk/i.test(s))     return `<span style="color:#60a5fa">${esc(s)}</span>`;
    if (/verdict/i.test(s))                            return `<span style="color:#fbbf24">${esc(s)}</span>`;
    if (/===|---/.test(s))                             return `<span style="color:#374151">${esc(s)}</span>`;
    if (/^\s*(if |else|->)/.test(s))                   return `<span style="color:#c084fc">${esc(s)}</span>`;
    if (/#/.test(s) && /%/.test(s))                    return `<span style="color:#6ee7b7">${esc(s)}</span>`;
    return `<span style="color:#9ca3af">${esc(s)}</span>`;
  };
  const lines = output.trim().split('\n');
  const linesHtml = lines.map((l, i) =>
    `<div class="ln" id="l${i}">${colorLine(l) || '&nbsp;'}</div>`
  ).join('');

  return { html: `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:#070707;color:#e5e7eb;font-family:'Cascadia Code','Consolas',monospace;
         font-size:12.5px;line-height:1.52;padding:22px 28px;height:720px;overflow:hidden}
    .hdr{color:${accentColor};font-size:1.05em;font-weight:800;margin-bottom:10px;letter-spacing:-.01em}
    .prompt{color:#374151;margin-bottom:3px;font-size:.88em}
    .cmd{color:#60a5fa;margin-bottom:14px;font-size:.88em}
    .ln{display:none;white-space:pre-wrap;word-break:break-all}
    .visible{display:block!important}
  </style></head><body>
  <div class="hdr">${esc(title)}</div>
  <div class="prompt">$ cd portfolio-risk-manager/${cmd.startsWith('python backtest') ? 'backtest' : 'ml'}</div>
  <div class="cmd">$ ${esc(cmd)}</div>
  <div id="out">${linesHtml}</div>
  </body></html>`, lines };
}

// ── main recording ────────────────────────────────────────────────────────
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--no-sandbox','--disable-gpu'] });
  const ctx  = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await ctx.newPage();

  // ════════════════════════════════════════════════════════════════════
  // SCENE 1 — Title slide (4 s)
  // ════════════════════════════════════════════════════════════════════
  console.log('Scene 1: title slide');
  await page.goto(`file://${SLIDES}`);
  await sleep(1400);
  await hold(page, 4000);

  // ════════════════════════════════════════════════════════════════════
  // SCENE 2 — Problem slide + What it does (2 slides)
  // ════════════════════════════════════════════════════════════════════
  console.log('Scene 2: problem + solution slides');
  for (let i = 0; i < 2; i++) {
    await page.keyboard.press('ArrowRight');
    await sleep(600); await hold(page, 2200);
  }

  // ════════════════════════════════════════════════════════════════════
  // SCENE 3 — Terminal: backtest canonical path
  // ════════════════════════════════════════════════════════════════════
  console.log('Scene 3: backtest canonical');
  const s3 = termPage(
    'Portfolio Risk Backtest — canonical path (540 days)',
    'python backtest.py --spec ../examples/sample_risk_spec.json',
    OUT_BT, '#34d399'
  );
  await page.setContent(s3.html);
  await sleep(300);
  await hold(page, 600); // show header
  for (let i = 0; i < s3.lines.length; i++) {
    await page.evaluate(i => { const e=document.getElementById('l'+i); if(e) e.classList.add('visible'); }, i);
    const delay = /===|---/.test(s3.lines[i]) ? 40 : /Sharpe|Drawdown|Calmar/i.test(s3.lines[i]) ? 180 : 55;
    await hold(page, delay);
  }
  await hold(page, 3500); // hold final results

  // ════════════════════════════════════════════════════════════════════
  // SCENE 4 — Terminal: Monte Carlo 200 paths
  // ════════════════════════════════════════════════════════════════════
  console.log('Scene 4: Monte Carlo');
  const s4 = termPage(
    'Monte Carlo Robustness — 200 randomized paths',
    'python backtest.py --mc 200',
    OUT_MC, '#60a5fa'
  );
  await page.setContent(s4.html);
  await sleep(300); await hold(page, 500);
  for (let i = 0; i < s4.lines.length; i++) {
    await page.evaluate(i => { const e=document.getElementById('l'+i); if(e) e.classList.add('visible'); }, i);
    const delay = /===|---/.test(s4.lines[i]) ? 40 : /Sharpe|Drawdown|beat|uplift/i.test(s4.lines[i]) ? 220 : 70;
    await hold(page, delay);
  }
  await hold(page, 3500);

  // ════════════════════════════════════════════════════════════════════
  // SCENE 5 — Slides: CMC tools + regime
  // ════════════════════════════════════════════════════════════════════
  console.log('Scene 5: CMC + regime slides');
  await page.goto(`file://${SLIDES}`);
  await sleep(1000);
  // jump to slide 4 (CMC tools)
  for (let i = 0; i < 3; i++) { await page.keyboard.press('ArrowRight'); await sleep(300); }
  await hold(page, 2500);
  await page.keyboard.press('ArrowRight'); await sleep(600);
  await hold(page, 2500); // regime slide

  // ════════════════════════════════════════════════════════════════════
  // SCENE 6 — Terminal: ML regime classifier
  // ════════════════════════════════════════════════════════════════════
  console.log('Scene 6: ML regime');
  const s6 = termPage(
    'ML Crash Classifier — Random Forest (from scratch, walk-forward OOS)',
    'python ml_regime.py',
    OUT_ML, '#a78bfa'
  );
  await page.setContent(s6.html);
  await sleep(300); await hold(page, 500);
  for (let i = 0; i < s6.lines.length; i++) {
    await page.evaluate(i => { const e=document.getElementById('l'+i); if(e) e.classList.add('visible'); }, i);
    const l = s6.lines[i];
    const delay = /===|---/.test(l) ? 35
                : /AUC|Sharpe|Drawdown|Calmar|importan/i.test(l) ? 200
                : /if |else|->/.test(l) ? 90
                : 50;
    await hold(page, delay);
  }
  await hold(page, 4000);

  // ════════════════════════════════════════════════════════════════════
  // SCENE 7 — Terminal: ATR Ridge vol forecaster
  // ════════════════════════════════════════════════════════════════════
  console.log('Scene 7: vol forecaster');
  const s7 = termPage(
    'ATR-based Ridge Volatility Forecaster — walk-forward OOS (R²>0)',
    'python vol_forecast.py',
    OUT_VOL, '#f0b429'
  );
  await page.setContent(s7.html);
  await sleep(300); await hold(page, 500);
  for (let i = 0; i < s7.lines.length; i++) {
    await page.evaluate(i => { const e=document.getElementById('l'+i); if(e) e.classList.add('visible'); }, i);
    const l = s7.lines[i];
    const delay = /===|---/.test(l) ? 35
                : /R2|RMSE|Sharpe|Drawdown|Calmar|ridge|ewma|feature/i.test(l) ? 200
                : 55;
    await hold(page, delay);
  }
  await hold(page, 4000);

  // ════════════════════════════════════════════════════════════════════
  // SCENE 8 — Results + summary slides (slides 6 and 14)
  // ════════════════════════════════════════════════════════════════════
  console.log('Scene 8: results + summary');
  await page.goto(`file://${SLIDES}`);
  await sleep(1000);
  // jump to slide 6 (results)
  for (let i = 0; i < 5; i++) { await page.keyboard.press('ArrowRight'); await sleep(250); }
  await hold(page, 3500);
  // jump to slide 14 (summary)
  for (let i = 0; i < 8; i++) { await page.keyboard.press('ArrowRight'); await sleep(200); }
  await hold(page, 4000);

  await ctx.close();
  await browser.close();

  // ── encode ───────────────────────────────────────────────────────────
  console.log(`\nEncoding ${fi} frames...`);
  const mp4 = path.join(OUT, 'demo.mp4');
  spawnSync('ffmpeg', [
    '-y', '-framerate', '24',
    '-i', path.join(FRAMES, 'frame_%05d.png'),
    '-vf', 'scale=1280:720,format=yuv420p',
    '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
    mp4
  ], { stdio: 'inherit' });

  const mb = (fs.statSync(mp4).size / 1e6).toFixed(1);
  console.log(`\nVideo ready: ${mp4}  (${mb} MB, ~${Math.round(fi/24)}s)`);
  spawnSync('cmd', ['/c', 'start', '', mp4], { stdio: 'ignore' });
})();
