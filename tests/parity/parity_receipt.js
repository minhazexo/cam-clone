global.self = global;
/* Receipt regression harness: the canvas pixel budget on the JS side.
 *
 * A long, narrow page (400x8000) is widened by reframe_like_reference to the
 * reference aspect — 54 MP before the REF_CANVAS_MAX_PIXELS budget, which
 * exhausted the worker's 1 GB WASM heap and surfaced as
 * "Scan worker failed: <raw C++ exception pointer>". This harness locks the
 * fixed behaviour:
 *
 *   1. reframe output dims == Python's (tests/fixtures/receipt_dims.json)
 *   2. the re-framed canvas stays within REF_CANVAS_MAX_PIXELS
 *   3. the full JS pipeline (processPage) completes and matches Python's
 *      output dims — i.e. the input that used to crash now scans.
 *
 * The input generator mirrors make_receipt() in tests/unit/test_scanner.py;
 * keep them identical. The anchor JSON is produced by
 * scripts/gen_receipt_fixture.py (regenerate ONLY with an intentional
 * pipeline change — see docs/TESTING.md). Exit nonzero on failure.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const FIX = path.join(ROOT, 'tests', 'fixtures');
const OPENCV_ABS = path.join(ROOT, 'static', 'vendor', 'opencv.js');
const GEOM_ABS = path.join(ROOT, 'static', 'js', 'workers', 'scan-geometry.js');
const WORKER_ABS = path.join(ROOT, 'static', 'js', 'workers', 'scan-worker-v2.js');
const REF_ASPECT = 893.0 / 1263.0;
const REF_CANVAS_MAX_PIXELS = 16000000;

function main() {
  const anchor = JSON.parse(fs.readFileSync(path.join(FIX, 'receipt_dims.json'), 'utf8'));
  const cvMod = require(OPENCV_ABS);
  cvMod.then(() => {
    try { runAll(cvMod, anchor); }
    catch (e) { console.error('parity_receipt ERROR:', (e && e.stack) || e); process.exit(1); }
  });
}

/** Canonical receipt — byte-for-byte mirror of tests/unit/test_scanner.py. */
function makeReceipt(w, h) {
  const rgba = new Uint8Array(w * h * 4);
  for (let i = 0; i < rgba.length; i += 4) {
    rgba[i] = 235; rgba[i + 1] = 235; rgba[i + 2] = 235; rgba[i + 3] = 255;
  }
  for (let y = 100; y < h - 100; y += 52) {
    for (let x = 60; x < 340; x++) {
      const i = (y * w + x) * 4;
      rgba[i] = rgba[i + 1] = rgba[i + 2] = 40;
    }
  }
  for (let y = 60; y < 64; y++) {
    for (let x = 20; x < 380; x++) {
      const i = (y * w + x) * 4;
      rgba[i] = 235; rgba[i + 1] = 130; rgba[i + 2] = 235;
    }
  }
  return rgba;
}

function runAll(cv, anchor) {
  globalThis.cv = cv;
  globalThis.RScanGeometry = require(GEOM_ABS)(cv);
  const G = globalThis.RScanGeometry;
  const worker = require(WORKER_ABS);
  let failures = 0;
  const check = (name, cond, msg) => {
    console.log(`${cond ? 'ok' : 'FAIL'} ${name}: ${msg}`);
    if (!cond) failures++;
  };

  const w = anchor.w, h = anchor.h;
  const rgba = makeReceipt(w, h);

  // 1+2) reframe on the raw receipt, exactly as the pipeline calls it first.
  const rgb = new Uint8Array(w * h * 3);
  for (let i = 0, j = 0; i < rgba.length; i += 4, j += 3) {
    rgb[j] = rgba[i]; rgb[j + 1] = rgba[i + 1]; rgb[j + 2] = rgba[i + 2];
  }
  const src = cv.matFromArray(h, w, cv.CV_8UC3, rgb);
  const framed = G.reframeLikeReference(src, { refAspect: REF_ASPECT });
  const area = framed.cols * framed.rows;
  check('reframe:dims', framed.cols === anchor.reframe[0] && framed.rows === anchor.reframe[1],
    `${framed.cols}x${framed.rows} vs py ${anchor.reframe[0]}x${anchor.reframe[1]}`);
  check('reframe:budget', area <= REF_CANVAS_MAX_PIXELS,
    `${area} px <= ${REF_CANVAS_MAX_PIXELS}`);
  framed.delete(); src.delete();

  // 3) the full worker pipeline — this input used to die with a raw
  //    C++ exception pointer ("Scan worker failed: 372817952").
  const t0 = Date.now();
  const res = worker.processPage(rgba, w, h);
  const ms = Date.now() - t0;
  check('full:dims', res.width === anchor.full[0] && res.height === anchor.full[1],
    `${res.width}x${res.height} vs py ${anchor.full[0]}x${anchor.full[1]} (${ms} ms)`);

  if (failures) process.exit(1);
  console.log('parity_receipt: all gates passed');
}

main();
