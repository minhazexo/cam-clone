global.self=global;
/* Step 2 parity harness: worker photometry vs Python photometry bytes.
 *
 * Loads static/vendor/opencv.js (absolute path, init via cv.then), sets
 * globalThis.cv, requires static/js/scan-worker-v2.js, runs processImage on
 * both fixture .rgb inputs and gates:
 *   - mean-abs-diff vs exp .rgb <= 3.0
 *   - output dims equal fixture dims
 *   - output sharpness (inline cv.Laplacian variance) within +-10% of the
 *     Python photometry sharpness from <name>.json
 * Exit nonzero on failure.
 *
 * NOTE on baselines: the plan's sharp numbers (tilt_ruled 1121->1829,
 * tilt_plain 1110->2125) are FULL-pipeline outputs (geometry + reframe
 * changes dims to 808x1143 / 738x1044 and resampling changes sharpness).
 * Step 2 ports photometry only, so its expected bytes are the photometry-only
 * exp_*.rgb (800x1100, sharp ~2315/~2221). Gating a geometry-free stage on
 * post-geometry sharpness would reject even a bit-exact port; the full-pipeline
 * numbers are printed below for reference and gated in Step 3+.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const FIX = path.join(ROOT, 'tests', 'fixtures');
const OPENCV_ABS = path.join(ROOT, 'static', 'vendor', 'opencv.js');
const WORKER_ABS = path.join(ROOT, 'static', 'js', 'scan-worker-v2.js');

// Full-pipeline Python baselines from scripts/gen_fixtures.py (reference only).
const FULL_BASELINES = {
  tilt_ruled: { tilt: 0.0, sharpIn: 1121.3, sharpOut: 1829.1, w: 808, h: 1143 },
  tilt_plain: { tilt: -0.89, sharpIn: 1109.9, sharpOut: 2124.6, w: 738, h: 1044 },
};

function laplacianSharpness(cv, rgbBytes, w, h) {
  const src = cv.matFromArray(h, w, cv.CV_8UC3, Buffer.from(rgbBytes));
  const gray = new cv.Mat();
  const lap = new cv.Mat();
  try {
    cv.cvtColor(src, gray, cv.COLOR_RGB2GRAY);
    cv.Laplacian(gray, lap, cv.CV_64F);
    const d = lap.data64F;
    let mean = 0;
    for (let i = 0; i < d.length; i++) mean += d[i];
    mean /= d.length;
    let va = 0;
    for (let i = 0; i < d.length; i++) {
      const t = d[i] - mean;
      va += t * t;
    }
    return va / d.length;
  } finally {
    src.delete();
    gray.delete();
    lap.delete();
  }
}

function main() {
  // Init via cv.then (callback chain only): this Emscripten build's thenable
  // must not be awaited — `await` on it deadlocks the Node event loop.
  const cvMod = require(OPENCV_ABS);
  cvMod.then(() => {
    try {
      runAll(cvMod);
    } catch (e) {
      console.error('parity_worker ERROR:', (e && e.stack) || e);
      process.exit(1);
    }
  });
}

function runAll(cv) {
  globalThis.cv = cv;
  const worker = require(WORKER_ABS);

  let failures = 0;
  for (const name of ['tilt_ruled', 'tilt_plain']) {
    const meta = JSON.parse(fs.readFileSync(path.join(FIX, `${name}.json`), 'utf8'));
    const { w, h } = meta;
    const inRgb = fs.readFileSync(path.join(FIX, `in_${name}.rgb`));
    const expRgb = fs.readFileSync(path.join(FIX, `exp_${name}.rgb`));
    if (inRgb.length !== w * h * 3 || expRgb.length !== w * h * 3) {
      console.error(`FAIL ${name}: fixture byte size mismatch (w=${w} h=${h})`);
      failures++;
      continue;
    }
    const rgba = new Uint8Array(w * h * 4);
    for (let i = 0, j = 0; i < inRgb.length; i += 3, j += 4) {
      rgba[j] = inRgb[i];
      rgba[j + 1] = inRgb[i + 1];
      rgba[j + 2] = inRgb[i + 2];
      rgba[j + 3] = 255;
    }
    const t0 = Date.now();
    const res = worker.processImage(rgba, w, h);
    const ms = Date.now() - t0;
    if (res.width !== w || res.height !== h) {
      console.error(`FAIL ${name}: dims ${res.width}x${res.height} != ${w}x${h}`);
      failures++;
      continue;
    }
    const outRgb = Buffer.alloc(w * h * 3);
    for (let i = 0, j = 0; i < outRgb.length; i += 3, j += 4) {
      outRgb[i] = res.data[j];
      outRgb[i + 1] = res.data[j + 1];
      outRgb[i + 2] = res.data[j + 2];
    }
    let mad = 0;
    for (let i = 0; i < outRgb.length; i++) mad += Math.abs(outRgb[i] - expRgb[i]);
    mad /= outRgb.length;
    const sharpOut = laplacianSharpness(cv, outRgb, w, h);
    const sharpExp = laplacianSharpness(cv, expRgb, w, h);
    const relExp = Math.abs(sharpOut - sharpExp) / sharpExp;
    const relPhoto = Math.abs(sharpOut - meta.sharp_photo) / meta.sharp_photo;
    const fb = FULL_BASELINES[name];
    console.log(
      `${name}: MAD=${mad.toFixed(3)} (gate <=3.0) dims=${res.width}x${res.height} ` +
      `sharp_out=${sharpOut.toFixed(1)} sharp_exp_rgb=${sharpExp.toFixed(1)} ` +
      `py_photo=${meta.sharp_photo.toFixed(1)} dExp=${(100 * relExp).toFixed(2)}% ` +
      `full_baseline=${meta.sharp_in.toFixed(0)}->${fb.sharpOut} (${fb.w}x${fb.h}) ${ms}ms`
    );
    let ok = true;
    if (!(mad <= 3.0)) { console.error(`FAIL ${name}: MAD ${mad} > 3.0`); ok = false; }
    if (!(relPhoto <= 0.10)) { console.error(`FAIL ${name}: sharpness off py_photo by ${(100 * relPhoto).toFixed(2)}%`); ok = false; }
    if (!(sharpOut > meta.sharp_in)) { console.error(`FAIL ${name}: no enhancement (sharp_out <= sharp_in)`); ok = false; }
    if (res.data.length !== w * h * 4) { console.error(`FAIL ${name}: RGBA length wrong`); ok = false; }
    console.log(`${name}: ${ok ? 'PASS' : 'FAIL'}`);
    if (!ok) failures++;
  }
  if (failures) {
    console.error(`${failures} fixture(s) FAILED`);
    process.exit(1);
  }
  console.log('parity_worker: ALL PASS');
  process.exit(0);
}

main();
