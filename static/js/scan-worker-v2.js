"use strict";
if (typeof importScripts === 'function') {
  importScripts('/static/vendor/opencv.js');
  importScripts('/static/js/scan-geometry.js');
}
// Geometry module: worker global (importScripts order above) or Node harness
// (sets globalThis.RScanGeometry before requiring this file).
function GEO() {
  if (typeof RScanGeometry !== 'undefined') return RScanGeometry;
  throw new Error('scan-geometry.js not loaded');
}

/* Step 2 photometry port of RScan/Python/scan/auto_scan.py — same math, same constants.
 *
 * Ports ONLY: high_pass_flatten (cv.blur box math, separable), white_point_stretch
 * (DEFAULT_WHITE_POINT=127), black_point_stretch (66, twice with BLACK_POINT2=20),
 * auto_black_point (pct=8.0, sort-based percentile), enhance_reference_look
 * (ksize default 101, saturate=1.25), plus the scale-1.0 light unsharp
 * (Gaussian sigma 0.8, addWeighted 1.3/-0.3).
 *
 * Works in RGB: the pipeline math is channel-symmetric, so BGR<->RGB order does
 * not matter. Worker protocol: onmessage {width,height,pixels:ArrayBuffer RGBA}
 * -> posts {width,height,pixels:ArrayBuffer RGBA, stats:{sharpness}}.
 * Alpha is stripped on input, re-added opaque (255) on output.
 *
 * Mat discipline: every cv.Mat is deleted in try/finally. One leaked Mat per
 * page = tab crash on big PDFs.
 */

// Defaults matching the original RScan GCMODE (auto_scan.py lines 26-31).
var DEFAULT_WHITE_POINT = 127;
var DEFAULT_BLACK_POINT = 66;
var DEFAULT_BLACK_POINT2 = 20;
var DEFAULT_SATURATE = 1.25;
var DEFAULT_KSIZE_DIVISOR = 8;

function oddKernel(minDim, divisor, minimum, maximum) {
  if (divisor === undefined || divisor === null) divisor = DEFAULT_KSIZE_DIVISOR;
  if (minimum === undefined || minimum === null) minimum = 21;
  if (maximum === undefined || maximum === null) maximum = 101;
  var ksize = Math.max(minimum, Math.floor(minDim / divisor));
  ksize = Math.min(maximum, ksize);
  if (ksize % 2 === 0) ksize += 1;
  return ksize;
}

// Mirror of np.clip(x, 0, 255) on a float32 Mat (exact for floats).
function clipFloat(m) {
  cv.threshold(m, m, 0, 255, cv.THRESH_TOZERO);
  cv.threshold(m, m, 255, 255, cv.THRESH_TRUNC);
}

// Mirror of np.clip(x, 0, 255).astype(np.uint8) (truncation, not rounding).
function truncateFloatToU8(floatMat) {
  var out = new cv.Mat(floatMat.rows, floatMat.cols, cv.CV_8UC3);
  var src = floatMat.data32F;
  var dst = out.data;
  for (var i = 0; i < dst.length; i++) {
    var v = src[i];
    dst[i] = v <= 0 ? 0 : v >= 255 ? 255 : Math.floor(v);
  }
  return out;
}

// Flatten uneven lighting: img - background + 127, per channel.
// NOTE: cv.blur with ksize, NOT filter2D — identical box math, separable.
function highPassFlatten(src, ksize) {
  if (ksize === undefined || ksize === null) {
    ksize = oddKernel(Math.min(src.rows, src.cols));
  }
  if (ksize % 2 === 0) ksize += 1;
  var bg = new cv.Mat();
  var fSrc = new cv.Mat();
  var fBg = new cv.Mat();
  var flatF = new cv.Mat();
  try {
    cv.blur(src, bg, new cv.Size(ksize, ksize));
    src.convertTo(fSrc, cv.CV_32FC3);
    bg.convertTo(fBg, cv.CV_32FC3);
    cv.subtract(fSrc, fBg, fSrc);
    fSrc.convertTo(flatF, cv.CV_32FC3, 1.0, 127.0);
    return truncateFloatToU8(flatF);
  } finally {
    bg.delete();
    fSrc.delete();
    fBg.delete();
    flatF.delete();
  }
}

// TRUNC highlights above white_point, then stretch [0, wp] -> [0, 255].
function whitePointStretch(src, whitePoint) {
  if (whitePoint === undefined || whitePoint === null) whitePoint = DEFAULT_WHITE_POINT;
  var wp = Math.min(255, Math.max(1, whitePoint));
  var truncated = new cv.Mat();
  var f = new cv.Mat();
  try {
    cv.threshold(src, truncated, wp, 255, cv.THRESH_TRUNC);
    truncated.convertTo(f, cv.CV_32FC3);
    f.convertTo(f, cv.CV_32FC3, 255.0 / wp, 0);
    clipFloat(f);
    return truncateFloatToU8(f);
  } finally {
    truncated.delete();
    f.delete();
  }
}

// Push shadows to black: (img - bp) * 255 / (255 - bp).
function blackPointStretch(src, blackPoint) {
  if (blackPoint === undefined || blackPoint === null) blackPoint = DEFAULT_BLACK_POINT;
  var bp = Math.min(254, Math.max(0, blackPoint));
  if (bp <= 0) return src.clone();
  var f = new cv.Mat();
  try {
    src.convertTo(f, cv.CV_32FC3);
    f.convertTo(f, cv.CV_32FC3, 1.0, -bp);
    f.convertTo(f, cv.CV_32FC3, 255.0 / (255.0 - bp), 0);
    clipFloat(f);
    return truncateFloatToU8(f);
  } finally {
    f.delete();
  }
}

// Pick a black point from the dark-text tail of the histogram (sort-based
// percentile mirroring np.percentile linear interpolation; clamped 10..120).
function autoBlackPoint(src, pct) {
  if (pct === undefined || pct === null) pct = 8.0;
  var gray = new cv.Mat();
  try {
    cv.cvtColor(src, gray, cv.COLOR_RGB2GRAY);
    var arr = new Uint8Array(gray.data);
    arr.sort();
    var n = arr.length;
    var rank = (n - 1) * (pct / 100);
    var lo = Math.floor(rank);
    var hi = Math.ceil(rank);
    var value = arr[lo] + (arr[hi] - arr[lo]) * (rank - lo);
    return Math.min(120, Math.max(10, value));
  } finally {
    gray.delete();
  }
}

// Per-channel chroma boost around the mean, mirroring the numpy float32 math
// bit-closely via Math.fround (lum=(r+g+b)/3, out=lum+(c-lum)*saturate).
function saturateBoostInPlace(m, saturate) {
  var d = m.data32F;
  for (var i = 0; i < d.length; i += 3) {
    var r = d[i], g = d[i + 1], b = d[i + 2];
    var lum = Math.fround(Math.fround(Math.fround(r + g) + b) / 3);
    d[i] = Math.fround(lum + Math.fround(Math.fround(r - lum) * saturate));
    d[i + 1] = Math.fround(lum + Math.fround(Math.fround(g - lum) * saturate));
    d[i + 2] = Math.fround(lum + Math.fround(Math.fround(b - lum) * saturate));
  }
}

// Photometric pass reproducing the reference's white background.
function enhanceReferenceLook(src, opts) {
  opts = opts || {};
  var ksize = (opts.ksize === undefined || opts.ksize === null) ? 101 : opts.ksize;
  var saturate = (opts.saturate === undefined || opts.saturate === null) ? DEFAULT_SATURATE : opts.saturate;
  var wp = (opts.whitePoint === undefined || opts.whitePoint === null) ? DEFAULT_WHITE_POINT : opts.whitePoint;
  var bp = (opts.blackPoint === undefined || opts.blackPoint === null) ? DEFAULT_BLACK_POINT : opts.blackPoint;
  var bp2 = (opts.blackPoint2 === undefined || opts.blackPoint2 === null) ? DEFAULT_BLACK_POINT2 : opts.blackPoint2;
  var flat = highPassFlatten(src, ksize);
  var cur = new cv.Mat();
  try {
    flat.convertTo(cur, cv.CV_32FC3);
    if (Math.abs(saturate - 1.0) > 1e-6) saturateBoostInPlace(cur, saturate);
    cv.threshold(cur, cur, wp, 255, cv.THRESH_TRUNC);
    cur.convertTo(cur, cv.CV_32FC3, 255.0 / wp, 0);
    clipFloat(cur);
    cur.convertTo(cur, cv.CV_32FC3, 1.0, -bp);
    cur.convertTo(cur, cv.CV_32FC3, 255.0 / (255.0 - bp), 0);
    clipFloat(cur);
    cur.convertTo(cur, cv.CV_32FC3, 1.0, -bp2);
    cur.convertTo(cur, cv.CV_32FC3, 255.0 / (255.0 - bp2), 0);
    clipFloat(cur);
    cv.threshold(cur, cur, 0, 255, cv.THRESH_TOZERO);
    return truncateFloatToU8(cur);
  } finally {
    flat.delete();
    cur.delete();
  }
}

// Scale-1.0 light unsharp: Gaussian sigma 0.8, addWeighted 1.3/-0.3.
function unsharpLight(src) {
  var blur = new cv.Mat();
  var out = null;
  try {
    cv.GaussianBlur(src, blur, new cv.Size(0, 0), 0.8, 0);
    out = new cv.Mat();
    cv.addWeighted(src, 1.3, blur, -0.3, 0, out);
    var res = out;
    out = null;
    return res;
  } finally {
    blur.delete();
    if (out) out.delete();
  }
}

// Laplacian variance of an RGB Mat (population variance, like ndarray.var()).
function sharpnessOf(src) {
  var gray = new cv.Mat();
  var lap = new cv.Mat();
  try {
    cv.cvtColor(src, gray, cv.COLOR_RGB2GRAY);
    cv.Laplacian(gray, lap, cv.CV_64F);
    var d = lap.data64F;
    var mean = 0;
    var i;
    for (i = 0; i < d.length; i++) mean += d[i];
    mean /= d.length;
    var va = 0;
    for (i = 0; i < d.length; i++) {
      var t = d[i] - mean;
      va += t * t;
    }
    return va / d.length;
  } finally {
    gray.delete();
    lap.delete();
  }
}

// Full Step-2 photometry: enhance + scale-1.0 light unsharp. Strips alpha on
// input, re-adds opaque alpha (255) on output.
function processImage(rgba, w, h) {
  var bytes = rgba instanceof Uint8Array ? rgba : new Uint8Array(rgba);
  if (bytes.length !== w * h * 4) {
    throw new Error('processImage: expected ' + (w * h * 4) + ' bytes, got ' + bytes.length);
  }
  var rgb = new Uint8Array(w * h * 3);
  for (var i = 0, j = 0; i < bytes.length; i += 4, j += 3) {
    rgb[j] = bytes[i];
    rgb[j + 1] = bytes[i + 1];
    rgb[j + 2] = bytes[i + 2];
  }
  var src = cv.matFromArray(h, w, cv.CV_8UC3, rgb);
  var enh = null;
  var sharp = null;
  try {
    enh = enhanceReferenceLook(src);
    sharp = unsharpLight(enh);
    var sharpness = sharpnessOf(sharp);
    var sdata = sharp.data;
    var out = new Uint8ClampedArray(w * h * 4);
    for (var p = 0, q = 0; p < sdata.length; p += 3, q += 4) {
      out[q] = sdata[p];
      out[q + 1] = sdata[p + 1];
      out[q + 2] = sdata[p + 2];
      out[q + 3] = 255;
    }
    return { data: out, width: w, height: h, sharpness: sharpness };
  } finally {
    src.delete();
    if (enh) enh.delete();
    if (sharp) sharp.delete();
  }
}

// Python int(round(x)) is banker's (half-to-even); 1px matters for parity.
function pyRound(x) {
  var f = Math.floor(x), d = x - f;
  if (d < 0.5) return f;
  if (d > 0.5) return f + 1;
  return (f % 2 === 0) ? f : f + 1;
}

var REF_ASPECT_FALLBACK = 893.0 / 1263.0;

// Full page pipeline (auto_scan.scan_photo_to_reference with output_scale=1.0,
// trim=true, reframe=true; SIFT template path skipped — stubbed null in
// geometry, matching reality with no reference asset). Returns RGBA + stats.
function processPage(rgba, w, h) {
  var bytes = rgba instanceof Uint8Array ? rgba : new Uint8Array(rgba);
  if (bytes.length !== w * h * 4) {
    throw new Error('processPage: expected ' + (w * h * 4) + ' bytes, got ' + bytes.length);
  }
  var G = GEO();
  var rgb = new Uint8Array(w * h * 3);
  for (var i = 0, j = 0; i < bytes.length; i += 4, j += 3) {
    rgb[j] = bytes[i];
    rgb[j + 1] = bytes[i + 1];
    rgb[j + 2] = bytes[i + 2];
  }
  var src = cv.matFromArray(h, w, cv.CV_8UC3, rgb);
  var working = null, enh = null, res = null, ref = null, rb = null, wc = null, wb = null, sharp = null;
  try {
    working = G.scanGeometryChain(src); // deletes src when replaced
    enh = enhanceReferenceLook(working);
    if (enh !== working) working.delete();
    res = G.residualDeskew(enh);
    if (res !== enh) enh.delete();
    ref = G.reframeLikeReference(res, { refAspect: REF_ASPECT_FALLBACK });
    if (ref !== res) res.delete();
    rb = G.removeBindingRings(ref);
    ref.delete();
    wc = G.whitenCornerSmears(rb.mat);
    rb.mat.delete();
    wb = G.whitenBorderArtifacts(wc);
    wc.delete();
    sharp = unsharpLight(wb);
    wb.delete();
    var targetW = pyRound(sharp.rows * REF_ASPECT_FALLBACK);
    if (targetW !== sharp.cols) {
      var fitted = new cv.Mat();
      cv.resize(sharp, fitted, new cv.Size(targetW, sharp.rows), 0, 0, cv.INTER_LANCZOS4);
      sharp.delete();
      sharp = fitted;
    }
    var sharpness = sharpnessOf(sharp);
    var sdata = sharp.data;
    var out = new Uint8ClampedArray(sharp.rows * sharp.cols * 4);
    for (var p = 0, q = 0; p < sdata.length; p += 3, q += 4) {
      out[q] = sdata[p];
      out[q + 1] = sdata[p + 1];
      out[q + 2] = sdata[p + 2];
      out[q + 3] = 255;
    }
    return { data: out, width: sharp.cols, height: sharp.rows, sharpness: sharpness };
  } finally {
    [src, working, enh, res, ref, rb && rb.mat, wc, wb, sharp].forEach(function (m) {
      try { if (m && !m.isDeleted()) m.delete(); } catch (e) { /*noop*/ }
    });
  }
}

if (typeof importScripts === 'function') {
  self.onmessage = function (e) {
    var msg = e.data || {};
    if (msg.ping) { // engine warmup probe: no pixels involved
      self.postMessage({ ready: true, engine: 'v2-full' });
      return;
    }
    try {
      var res = processPage(new Uint8Array(msg.pixels), msg.width, msg.height);
      self.postMessage(
        { width: res.width, height: res.height, pixels: res.data.buffer, stats: { sharpness: res.sharpness } },
        [res.data.buffer]
      );
    } catch (err) {
      self.postMessage({ error: String((err && err.message) || err) });
    }
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    processImage: processImage,
    processPage: processPage,
    enhanceReferenceLook: enhanceReferenceLook,
    highPassFlatten: highPassFlatten,
    whitePointStretch: whitePointStretch,
    blackPointStretch: blackPointStretch,
    autoBlackPoint: autoBlackPoint,
    unsharpLight: unsharpLight,
    sharpnessOf: sharpnessOf,
    oddKernel: oddKernel,
    DEFAULT_WHITE_POINT: DEFAULT_WHITE_POINT,
    DEFAULT_BLACK_POINT: DEFAULT_BLACK_POINT,
    DEFAULT_BLACK_POINT2: DEFAULT_BLACK_POINT2,
    DEFAULT_SATURATE: DEFAULT_SATURATE,
    DEFAULT_KSIZE_DIVISOR: DEFAULT_KSIZE_DIVISOR
  };
}
