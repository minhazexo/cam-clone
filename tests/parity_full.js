global.self=global;
/* Step 5 parity harness: full worker processPage vs Python full-pipeline bytes.
 * Gates per fixture: dims exact, MAD<=3.0, tilt (ruled ±0.15 of 0.00, plain
 * ±0.3 of -0.89 — resampling-sensitive), sharpness ±10% of full baselines.
 * Exit nonzero on failure.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const FIX = path.join(ROOT, 'tests', 'fixtures');
const OPENCV_ABS = path.join(ROOT, 'static', 'vendor', 'opencv.js');
const GEOM_ABS = path.join(ROOT, 'static', 'js', 'scan-geometry.js');
const WORKER_ABS = path.join(ROOT, 'static', 'js', 'scan-worker-v2.js');

const BASE = {
  // Regenerated after reframe-first binding order + post-enhance trim:
  // tighter second reframe shrinks both fixtures a few px.
  tilt_ruled: { tilt: 0.00, tiltTol: 0.15, sharp: 2002.2, w: 790, h: 1117 },
  tilt_plain: { tilt: 0.00, tiltTol: 0.15, sharp: 2078.8, w: 791, h: 1119 },
};

function main() {
  const cvMod = require(OPENCV_ABS);
  cvMod.then(() => {
    try { runAll(cvMod); }
    catch (e) { console.error('parity_full ERROR:', (e && e.stack) || e); process.exit(1); }
  });
}

function runAll(cv) {
  globalThis.cv = cv;
  globalThis.RScanGeometry = require(GEOM_ABS)(cv);
  const worker = require(WORKER_ABS);
  const G = globalThis.RScanGeometry;
  let failures = 0;
  const check = (name, cond, msg) => {
    console.log(`${cond ? 'ok' : 'FAIL'} ${name}: ${msg}`);
    if (!cond) failures++;
  };

  for (const name of ['tilt_ruled', 'tilt_plain']) {
    console.log('--- ' + name + ' ---');
    const meta = JSON.parse(fs.readFileSync(path.join(FIX, `${name}.json`), 'utf8'));
    const { w, h } = meta;
    const inRgb = fs.readFileSync(path.join(FIX, `in_${name}.rgb`));
    // full_*.rgb = complete Python pipeline bytes (geom+photo+reframe+cleanups
    // +unsharp+aspect-fit); exp_*.rgb is photometry-only (Step 2 gate).
    const expRgb = fs.readFileSync(path.join(FIX, `full_${name}.rgb`));
    const rgba = new Uint8Array(w * h * 4);
    for (let i = 0, j = 0; i < inRgb.length; i += 3, j += 4) {
      rgba[j] = inRgb[i]; rgba[j + 1] = inRgb[i + 1]; rgba[j + 2] = inRgb[i + 2]; rgba[j + 3] = 255;
    }
    const t0 = Date.now();
    const res = worker.processPage(rgba, w, h);
    const ms = Date.now() - t0;
    const b = BASE[name];
    check(name + ':dims', res.width === b.w && res.height === b.h,
      `${res.width}x${res.height} vs py ${b.w}x${b.h}`);
    let mad = Infinity;
    if (res.width === b.w && res.height === b.h) {
      const out = Buffer.alloc(b.w * b.h * 3);
      for (let i = 0, j = 0; i < out.length; i += 3, j += 4) {
        out[i] = res.data[j]; out[i + 1] = res.data[j + 1]; out[i + 2] = res.data[j + 2];
      }
      let s = 0;
      for (let i = 0; i < out.length; i++) s += Math.abs(out[i] - expRgb[i]);
      mad = s / out.length;
    }
    check(name + ':mad', mad <= 3.0, `MAD=${mad.toFixed(3)} (gate 3.0)`);
    // tilt + sharpness measured on the worker output via geometry estimator
    const m = cv.matFromArray(res.height, res.width, cv.CV_8UC3, Buffer.from(res.data.filter((_, i) => i % 4 !== 3)));
    let tilt = NaN, sharp = NaN;
    try {
      const g = new cv.Mat();
      cv.cvtColor(m, g, cv.COLOR_RGB2GRAY);
      const lap = new cv.Mat();
      cv.Laplacian(g, lap, cv.CV_64F);
      const d = lap.data64F;
      let mean = 0;
      for (let i = 0; i < d.length; i++) mean += d[i];
      mean /= d.length;
      let va = 0;
      for (let i = 0; i < d.length; i++) { const t = d[i] - mean; va += t * t; }
      sharp = va / d.length;
      g.delete(); lap.delete();
      tilt = G.estimateSkewAngle(m);
    } finally { m.delete(); }
    check(name + ':tilt', Math.abs(tilt - b.tilt) <= b.tiltTol, `tilt=${tilt.toFixed(2)} vs py ${b.tilt}`);
    check(name + ':sharp', Math.abs(sharp - b.sharp) / b.sharp <= 0.10,
      `sharp=${sharp.toFixed(1)} vs py ${b.sharp} (${ms}ms)`);
  }
  if (failures) { console.error(`${failures} check(s) FAILED`); process.exit(1); }
  console.log('parity_full: ALL PASS');
  process.exit(0);
}

main();
