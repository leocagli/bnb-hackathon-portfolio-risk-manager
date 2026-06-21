/**
 * Portfolio Risk Manager — Video Demo
 * Uses installed Microsoft Edge (no download) + ffmpeg to produce demo.mp4
 * Usage: node record_video.js
 */
const { chromium } = require('playwright');
const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const SLIDES  = path.resolve(__dirname, '../portfolio-risk-manager/slides/index.html');
const BT_DIR  = path.resolve(__dirname, '../portfolio-risk-manager/backtest');
const SPEC    = path.resolve(__dirname, '../portfolio-risk-manager/examples/sample_risk_spec.json');
const OUT     = path.resolve(__dirname, 'output');
const FRAMES  = path.join(OUT, 'frames');

[OUT, FRAMES].forEach(d => fs.existsSync(d) || fs.mkdirSync(d, { recursive: true }));

// ── helpers ────────────────────────────────────────────────────────────────
const sleep = ms => new Promise(r => setTimeout(r, ms));
let frameIdx = 0;
async function shot(page) {
  const f = path.join(FRAMES, `frame_${String(frameIdx++).padStart(4,'0')}.png`);
  await page.screenshot({ path: f });
  return f;
}
// hold a frame for N ms at ~24fps
async function hold(page, ms) {
  const n = Math.ceil(ms / (1000/24));
  const f = await shot(page);
  for (let i = 1; i < n; i++) fs.copyFileSync(f, path.join(FRAMES, `frame_${String(frameIdx++).padStart(4,'0')}.png`));
}

(async () => {
  // ── run backtest, capture output for terminal slide ──────────────────────
  let btOut = '';
  try {
    btOut = execSync(`python backtest.py --spec "${SPEC}"`, { cwd: BT_DIR, timeout: 30000 }).toString();
  } catch(e) { btOut = (e.stdout||'').toString(); }

  // ── launch Edge (already installed, no download) ─────────────────────────
  console.log('Launching Edge...');
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
    args: ['--no-sandbox','--disable-gpu']
  });
  const ctx  = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await ctx.newPage();

  // ── SCENE 1: title slide (3 s) ───────────────────────────────────────────
  console.log('Scene 1: title...');
  await page.goto(`file://${SLIDES}`);
  await sleep(1200);
  await hold(page, 3000);

  // ── SCENE 2: walk through slides 2-7 (1.8 s each) ───────────────────────
  console.log('Scene 2: slides 2-7...');
  for (let i = 2; i <= 7; i++) {
    await page.keyboard.press('ArrowRight');
    await sleep(700);
    await hold(page, 1800);
    process.stdout.write(`  slide ${i}\r`);
  }

  // ── SCENE 3: results slide (slide 6) held longer ─────────────────────────
  // already on slide 7 (results), hold 3 s more
  console.log('\nScene 3: hold results...');
  await hold(page, 2000);

  // ── SCENE 4: slides 8-14 ─────────────────────────────────────────────────
  console.log('Scene 4: slides 8-14...');
  for (let i = 8; i <= 14; i++) {
    await page.keyboard.press('ArrowRight');
    await sleep(700);
    await hold(page, 1600);
    process.stdout.write(`  slide ${i}\r`);
  }

  // ── SCENE 5: terminal overlay with backtest output ────────────────────────
  console.log('\nScene 5: terminal...');
  const termHtml = buildTerminal(btOut);
  await page.setContent(termHtml);
  await sleep(400);

  // reveal lines one by one
  const lines = btOut.trim().split('\n');
  for (let i = 0; i < lines.length; i++) {
    await page.evaluate(idx => {
      const el = document.getElementById('line-' + idx);
      if (el) el.style.display = 'block';
    }, i);
    await hold(page, i < 5 ? 300 : 120);
  }
  await hold(page, 2500); // hold final result

  await ctx.close();
  await browser.close();

  // ── encode with ffmpeg ───────────────────────────────────────────────────
  console.log(`\nEncoding ${frameIdx} frames with ffmpeg...`);
  const out = path.join(OUT, 'demo.mp4');
  const r = spawnSync('ffmpeg', [
    '-y',
    '-framerate', '24',
    '-i', path.join(FRAMES, 'frame_%04d.png'),
    '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
    '-c:v', 'libx264',
    '-preset', 'fast',
    '-crf', '20',
    out
  ], { stdio: 'inherit' });

  if (r.status === 0) {
    const mb = (fs.statSync(out).size / 1e6).toFixed(1);
    console.log(`\nVideo ready: ${out}  (${mb} MB)`);
    // open in default player
    spawnSync('cmd', ['/c', 'start', '', out], { stdio: 'ignore' });
  } else {
    console.error('ffmpeg failed — frames are in', FRAMES);
  }
})();

// ── terminal HTML builder ──────────────────────────────────────────────────
function buildTerminal(output) {
  const lines = output.trim().split('\n');
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  const colorLine = s => {
    if (/sharpe/i.test(s))      return `<span style="color:#34d399">${esc(s)}</span>`;
    if (/drawdown|max dd/i.test(s)) return `<span style="color:#f87171">${esc(s)}</span>`;
    if (/calmar|cagr/i.test(s)) return `<span style="color:#60a5fa">${esc(s)}</span>`;
    if (/overlay|risk/i.test(s))return `<span style="color:#f0b429">${esc(s)}</span>`;
    if (/==+/.test(s))          return `<span style="color:#374151">${esc(s)}</span>`;
    return `<span style="color:#9ca3af">${esc(s)}</span>`;
  };

  const linesHtml = lines.map((l, i) =>
    `<div id="line-${i}" style="display:none">${colorLine(l)}</div>`
  ).join('');

  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{background:#0a0a0a;margin:0;padding:28px 36px;font-family:'Cascadia Code','Consolas',monospace;font-size:13.5px;line-height:1.55}
  .header{color:#f0b429;font-size:1.3em;font-weight:800;margin-bottom:16px}
  .prompt{color:#4b5563;margin-bottom:8px;font-size:.9em}
  .cmd{color:#60a5fa;margin-bottom:16px;font-size:.9em}
</style></head><body>
<div class="header">Portfolio Risk Manager — Backtest</div>
<div class="prompt">$ cd portfolio-risk-manager/backtest</div>
<div class="cmd">$ python backtest.py --spec ../examples/sample_risk_spec.json</div>
${linesHtml}
</body></html>`;
}
