/* RScan geometry stage port (auto_scan.py) for the on-device pipeline.
 * RGB Mats throughout (canvas order). Dual-use: worker (importScripts AFTER
 * opencv.js) and Node (require(path)(cv)).
 *
 * OWNERSHIP: no function deletes its input. Functions return a NEW Mat, the
 * SAME Mat (documented no-op aliases: deskew@0, trims without cut, reframe
 * degenerate), or null (contour/dewarp/rectify miss). Callers own everything
 * and delete what they replace. scanGeometryChain() demonstrates the pattern.
 *
 * Intentionally omitted: align_to_reference_template is a null stub
 * (SIFT missing in WASM + no reference asset); trim_coil_margin IS ported
 * although currently uncalled by the pipeline (kept for parity).
 */
(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) module.exports = factory;
  else root.RScanGeometry = factory(root.cv);
})(typeof self !== 'undefined' ? self : globalThis, function (cv) {
  'use strict';

  var REF_MARGIN_LEFT = 0.069, REF_MARGIN_RIGHT = 0.071;
  var REF_MARGIN_TOP = 0.070, REF_MARGIN_BOTTOM = 0.040;
  var REF_ASPECT_FALLBACK = 893.0 / 1263.0;

  // ---------- JS math helpers ----------
  function clip(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
  // Python int() truncates (values here are non-negative => floor);
  // Python round() is banker's (half-to-even). Both matter: 1px paste/trim
  // offsets show up as MAD ~1 on page edges.
  function pyInt(x) { return Math.floor(x); }
  function pyRound(x) {
    var f = Math.floor(x), d = x - f;
    if (d < 0.5) return f;
    if (d > 0.5) return f + 1;
    return (f % 2 === 0) ? f : f + 1;
  }
  function hyp(x, y) { return Math.sqrt(x * x + y * y); }
  function wmedian(vals, wts) {
    var idx = vals.map(function (_, i) { return i; });
    idx.sort(function (a, b) { return vals[a] - vals[b]; });
    var total = 0, i;
    for (i = 0; i < wts.length; i++) total += wts[i];
    var acc = 0;
    for (i = 0; i < idx.length; i++) {
      acc += wts[idx[i]];
      if (acc >= total / 2.0) return vals[idx[i]];
    }
    return vals[idx[idx.length - 1]];
  }
  function polyfit(xs, ys) { // least squares y = m*x + c
    var n = xs.length, sx = 0, sy = 0, sxx = 0, sxy = 0, i;
    for (i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; sxx += xs[i] * xs[i]; sxy += xs[i] * ys[i]; }
    var den = n * sxx - sx * sx;
    if (Math.abs(den) < 1e-12) return [0, n ? sy / n : 0];
    var m = (n * sxy - sx * sy) / den;
    return [m, (sy - m * sx) / n];
  }
  function convolveSame(arr, ker) {
    var n = arr.length, k = ker.length, h = Math.floor(k / 2), out = new Array(n), i, j;
    for (i = 0; i < n; i++) {
      var s = 0;
      for (j = 0; j < k; j++) s += ker[j] * arr[clip(i + j - h, 0, n - 1)];
      out[i] = s;
    }
    return out;
  }
  function interp1(x, xp, fp) {
    if (x <= xp[0]) return fp[0];
    var n = xp.length;
    if (x >= xp[n - 1]) return fp[n - 1];
    var lo = 0;
    while (lo < n - 2 && xp[lo + 1] < x) lo++;
    var t = (x - xp[lo]) / (xp[lo + 1] - xp[lo] || 1e-12);
    return fp[lo] + t * (fp[lo + 1] - fp[lo]);
  }

  // ---------- cv helpers ----------
  function del() {
    for (var i = 0; i < arguments.length; i++) {
      try { var m = arguments[i]; if (m && !m.isDeleted()) m.delete(); } catch (e) { /*noop*/ }
    }
  }
  function grayOf(rgb) { var g = new cv.Mat(); cv.cvtColor(rgb, g, cv.COLOR_RGB2GRAY); return g; }
  function white3() { return new cv.Scalar(255, 255, 255); }
  function f32Mat(h, w, arr) {
    var m = new cv.Mat(h, w, cv.CV_32F);
    m.data32F.set(arr instanceof Float32Array ? arr : Float32Array.from(arr));
    return m;
  }

  // ---------- points / contour ----------
  function orderPoints(pts) { // pts: [[x,y]x4] -> [tl,tr,br,bl]
    var s = pts.map(function (p) { return p[0] + p[1]; });
    var d = pts.map(function (p) { return p[0] - p[1]; });
    var iMin = 0, iMax = 0, iDMax = 0, iDMin = 0, i;
    for (i = 1; i < 4; i++) {
      if (s[i] < s[iMin]) iMin = i;
      if (s[i] > s[iMax]) iMax = i;
      if (d[i] > d[iDMax]) iDMax = i;
      if (d[i] < d[iDMin]) iDMin = i;
    }
    return [pts[iMin], pts[iDMax], pts[iMax], pts[iDMin]];
  }

  function findDocumentContour(rgb, minAreaRatio) {
    if (minAreaRatio === undefined) minAreaRatio = 0.25;
    var h = rgb.rows, w = rgb.cols;
    var gray = grayOf(rgb);
    var blur = new cv.Mat(), edged = new cv.Mat(), kernel = cv.Mat.ones(3, 3, cv.CV_8U);
    var contours = new cv.MatVector(), hier = new cv.Mat();
    try {
      cv.GaussianBlur(gray, blur, new cv.Size(5, 5), 0);
      cv.Canny(blur, edged, 30, 120);
      cv.dilate(edged, edged, kernel, new cv.Point(-1, -1), 1);
      cv.findContours(edged, contours, hier, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
      var n = contours.size(), i, items = [];
      for (i = 0; i < n; i++) items.push(contours.get(i));
      items.sort(function (a, b) { return cv.contourArea(b) - cv.contourArea(a); });
      items = items.slice(0, 7);
      var imageArea = h * w, result = null;
      for (i = 0; i < items.length && !result; i++) {
        (function (cnt) {
          var area = cv.contourArea(cnt);
          if (area < minAreaRatio * imageArea || area > 0.995 * imageArea) return;
          var peri = cv.arcLength(cnt, true);
          var epsilons = [0.02, 0.03, 0.05], j;
          for (j = 0; j < epsilons.length && !result; j++) {
            var approx = new cv.Mat();
            cv.approxPolyDP(cnt, approx, epsilons[j] * peri, true);
            if (approx.rows === 4 && cv.isContourConvex(approx)) {
              var d = approx.data32S, pts = [];
              for (var k = 0; k < 4; k++) pts.push([d[k * 2], d[k * 2 + 1]]);
              result = orderPoints(pts);
            }
            del(approx);
          }
        })(items[i]);
      }
      items.forEach(function (c) { del(c); });
      return result;
    } finally {
      del(gray, blur, edged, kernel, contours, hier);
    }
  }

  function warpToRectangle(rgb, corners) {
    // 1% anti-clip expansion about the quad center (mirrors Python).
    var h0 = rgb.rows, w0 = rgb.cols, i;
    var cx = 0, cy = 0;
    for (i = 0; i < 4; i++) { cx += corners[i][0]; cy += corners[i][1]; }
    cx /= 4; cy /= 4;
    corners = corners.map(function (p) {
      return [
        Math.min(w0 - 1, Math.max(0, cx + (p[0] - cx) * 1.01)),
        Math.min(h0 - 1, Math.max(0, cy + (p[1] - cy) * 1.01))
      ];
    });
    var tl = corners[0], tr = corners[1], br = corners[2], bl = corners[3];
    var maxW = Math.max(1, pyInt(Math.max(hyp(br[0] - bl[0], br[1] - bl[1]), hyp(tr[0] - tl[0], tr[1] - tl[1]))));
    var maxH = Math.max(1, pyInt(Math.max(hyp(tr[0] - br[0], tr[1] - br[1]), hyp(tl[0] - bl[0], tl[1] - bl[1]))));
    var dst = cv.matFromArray(4, 2, cv.CV_32F, [0, 0, maxW - 1, 0, maxW - 1, maxH - 1, 0, maxH - 1]);
    var flat = [];
    corners.forEach(function (p) { flat.push(p[0], p[1]); });
    var src = cv.matFromArray(4, 2, cv.CV_32F, flat);
    var M = cv.getPerspectiveTransform(src, dst);
    var out = new cv.Mat();
    cv.warpPerspective(rgb, out, M, new cv.Size(maxW, maxH), cv.INTER_CUBIC, cv.BORDER_CONSTANT, new cv.Scalar(0, 0, 0));
    del(dst, src, M);
    return out;
  }

  // ---------- ruling analysis ----------
  function probeGray(rgb, targetWidth) {
    if (targetWidth === undefined) targetWidth = 1000;
    var gray = grayOf(rgb), scale = 1.0, mat = gray;
    if (gray.cols > targetWidth) {
      scale = targetWidth / gray.cols;
      mat = new cv.Mat();
      cv.resize(gray, mat, new cv.Size(0, 0), scale, scale, cv.INTER_AREA);
      del(gray);
    }
    return { mat: mat, scale: scale };
  }

  function adaptiveInkMask(blur) {
    var pw = blur.cols;
    var block = Math.max(21, pyInt(pw / 15));
    if (block % 2 === 0) block += 1;
    block = Math.min(block, 101);
    var out = new cv.Mat();
    cv.adaptiveThreshold(blur, out, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, cv.THRESH_BINARY_INV, block, 7);
    return out;
  }

  function rulingSegments(probe, maxTiltDeg) {
    if (maxTiltDeg === undefined) maxTiltDeg = 12.0;
    var blur = new cv.Mat();
    cv.GaussianBlur(probe, blur, new cv.Size(5, 5), 0);
    var bw = adaptiveInkMask(blur);
    var ph = bw.rows, pw = bw.cols;
    var kx = Math.max(30, pyInt(pw / 12));
    var k1 = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(kx, 1));
    var opened = new cv.Mat();
    cv.morphologyEx(bw, opened, cv.MORPH_OPEN, k1);
    var k2 = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(Math.max(15, Math.floor(kx / 2)), 1));
    var horiz = new cv.Mat();
    cv.morphologyEx(opened, horiz, cv.MORPH_CLOSE, k2);
    var lines = new cv.Mat();
    cv.HoughLinesP(horiz, lines, 1, Math.PI / 180, 80, Math.max(100, pyInt(pw / 4)), 30);
    var out = [], maxTilt = Math.tan(maxTiltDeg * Math.PI / 180);
    try {
      if (lines.rows > 0) {
        var d = lines.data32S, i;
        for (i = 0; i < lines.rows; i++) {
          var x1 = d[i * 4], y1 = d[i * 4 + 1], x2 = d[i * 4 + 2], y2 = d[i * 4 + 3];
          var dx = x2 - x1, dy = y2 - y1;
          if (dx < 0) { dx = -dx; dy = -dy; var t = x1; x1 = x2; x2 = t; t = y1; y1 = y2; y2 = t; }
          if (Math.abs(dx) < 2 * Math.abs(dy)) continue;
          if (Math.abs(dy / Math.max(dx, 1e-6)) > maxTilt) continue;
          var cy = (y1 + y2) / 2.0, cx = (x1 + x2) / 2.0;
          if (cy < 0.10 * ph || cy > 0.98 * ph) continue;
          if (cx < 0.03 * pw || cx > 0.97 * pw) continue;
          out.push([x1, y1, x2, y2]);
        }
      }
    } finally {
      del(blur, bw, k1, k2, opened, horiz, lines);
    }
    return out;
  }

  function fitLine(segments) {
    var xs = [], ys = [], i, s;
    for (i = 0; i < segments.length; i++) {
      s = segments[i];
      xs.push(s[0], s[2]); ys.push(s[1], s[3]);
    }
    return polyfit(xs, ys);
  }

  function dewarpByRulings(rgb, nBands, minBands) {
    if (nBands === undefined) nBands = 6;
    if (minBands === undefined) minBands = 3;
    var h = rgb.rows, w = rgb.cols;
    var probe = probeGray(rgb), i;
    try {
      var ph = probe.mat.rows, pw = probe.mat.cols;
      var segments = rulingSegments(probe.mat);
      var yLo = 0.06 * ph, yHi = 0.98 * ph;
      var slopes = [], centers = [];
      for (i = 0; i < nBands; i++) {
        var e0 = yLo + (yHi - yLo) * i / nBands, e1 = yLo + (yHi - yLo) * (i + 1) / nBands;
        var lo = e0 - 0.25 * (e1 - e0), hi = e1 + 0.25 * (e1 - e0);
        var band = segments.filter(function (s) { var m = (s[1] + s[3]) / 2.0; return m >= lo && m < hi; });
        centers.push((e0 + e1) / 2.0);
        if (band.length < 2) { slopes.push(null); continue; }
        var xs = [];
        band.forEach(function (s) { xs.push(s[0], s[2]); });
        if (Math.max.apply(null, xs) - Math.min.apply(null, xs) < 0.4 * pw) { slopes.push(null); continue; }
        var mc = fitLine(band);
        slopes.push(Math.abs(mc[0]) > Math.tan(12 * Math.PI / 180) ? null : mc[0]);
      }
      var good = slopes.filter(function (m) { return m !== null; });
      if (good.length < minBands) return null;
      var filled = slopes.map(function (m, idx) {
        if (m !== null) return m;
        var p = null, q = null, j;
        for (j = idx - 1; j >= 0; j--) if (slopes[j] !== null) { p = slopes[j]; break; }
        for (j = idx + 1; j < slopes.length; j++) if (slopes[j] !== null) { q = slopes[j]; break; }
        if (p !== null && q !== null) return (p + q) / 2.0;
        return p !== null ? p : q;
      });
      var arr = convolveSame(filled, [0.25, 0.5, 0.25]);
      var mapX = new Float32Array(h * w), mapY = new Float32Array(h * w), r, x;
      var cx = w / 2.0, kinv = ph / h;
      for (r = 0; r < h; r++) {
        var mOfY = interp1(r * kinv, centers, arr);
        for (x = 0; x < w; x++) {
          mapX[r * w + x] = x;
          mapY[r * w + x] = r + mOfY * (x - cx);
        }
      }
      var out = new cv.Mat();
      cv.remap(rgb, out, f32Mat(h, w, mapX), f32Mat(h, w, mapY),
        cv.INTER_CUBIC, cv.BORDER_CONSTANT, white3());
      return out;
    } finally {
      del(probe.mat);
    }
  }

  function rectifyFromRulings(rgb, maxTiltDeg) {
    if (maxTiltDeg === undefined) maxTiltDeg = 12.0;
    var h = rgb.rows, w = rgb.cols;
    var probe = probeGray(rgb);
    try {
      var ph = probe.mat.rows, pw = probe.mat.cols, scale = probe.scale;
      var segments = rulingSegments(probe.mat, maxTiltDeg);
      var top = segments.filter(function (s) { return (s[1] + s[3]) / 2.0 < 0.45 * ph; });
      var bottom = segments.filter(function (s) { return (s[1] + s[3]) / 2.0 > 0.55 * ph; });
      if (top.length < 2 || bottom.length < 2) return null;
      var bands = [top, bottom], b;
      for (b = 0; b < 2; b++) {
        var xs = [];
        bands[b].forEach(function (s) { xs.push(s[0], s[2]); });
        if (Math.max.apply(null, xs) - Math.min.apply(null, xs) < 0.5 * pw) return null;
      }
      var ft = fitLine(top), fb = fitLine(bottom);
      var mt = ft[0], ct = ft[1], mb = fb[0], cb = fb[1];
      var maxM = Math.tan(maxTiltDeg * Math.PI / 180);
      if (Math.abs(mt) > maxM || Math.abs(mb) > maxM) return null;
      if (Math.abs(mt - mb) > Math.tan(15 * Math.PI / 180)) return null;
      var inv = 1.0 / scale;
      var sx = [
        [0.0, ct * inv], [(pw - 1) * inv, (mt * (pw - 1) + ct) * inv],
        [(pw - 1) * inv, (mb * (pw - 1) + cb) * inv], [0.0, cb * inv]
      ];
      var yt = (sx[0][1] + sx[1][1]) / 2.0, yb = (sx[2][1] + sx[3][1]) / 2.0;
      if (yb - yt < 0.25 * h) return null;
      yt = clip(yt, 0, h - 1); yb = clip(yb, 0, h - 1);
      var srcM = cv.matFromArray(4, 2, cv.CV_32F,
        [sx[0][0], sx[0][1], sx[1][0], sx[1][1], sx[2][0], sx[2][1], sx[3][0], sx[3][1]]);
      var dstM = cv.matFromArray(4, 2, cv.CV_32F, [0, yt, w - 1, yt, w - 1, yb, 0, yb]);
      var M, out = new cv.Mat();
      try {
        M = cv.getPerspectiveTransform(srcM, dstM);
      } catch (e) { del(srcM, dstM, out); return null; }
      cv.warpPerspective(rgb, out, M, new cv.Size(w, h), cv.INTER_CUBIC, cv.BORDER_CONSTANT, white3());
      del(srcM, dstM, M);
      return out;
    } finally {
      del(probe.mat);
    }
  }

  // ---------- skew ----------
  function estimateSkewAngle(rgb, maxAngle) {
    if (maxAngle === undefined) maxAngle = 15.0;
    var probe = probeGray(rgb);
    try {
      var segments = rulingSegments(probe.mat, maxAngle);
      if (segments.length >= 5) {
        var angles = [], weights = [], i;
        for (i = 0; i < segments.length; i++) {
          var s = segments[i], dx = s[2] - s[0], dy = s[3] - s[1];
          angles.push(Math.atan2(dy, dx) * 180 / Math.PI);
          weights.push(hyp(dx, dy));
        }
        var median = wmedian(angles, weights);
        if (Math.abs(median) <= maxAngle && Math.abs(median) >= 0.3) return median;
      }
    } finally {
      del(probe.mat);
    }
    return estimateColorRulingTilt(rgb, Math.min(maxAngle, 10.0));
  }

  function estimateColorRulingTilt(rgb, maxAngle) {
    if (maxAngle === undefined) maxAngle = 10.0;
    var mv = new cv.MatVector(), r = null, g = null, b = null;
    try {
      cv.split(rgb, mv);
      if (mv.size() < 3) return 0.0;
      r = mv.get(0); g = mv.get(1); b = mv.get(2);
      var pink = new cv.Mat();
      cv.subtract(r, g, pink);
      var h = pink.rows, w = pink.cols, scale = 1.0;
      var work = pink;
      if (w > 1000) {
        scale = 1000.0 / w;
        work = new cv.Mat();
        cv.resize(pink, work, new cv.Size(0, 0), scale, scale, cv.INTER_AREA);
        del(pink);
      }
      var bw = new cv.Mat();
      cv.threshold(work, bw, 25, 255, cv.THRESH_BINARY);
      var k = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(15, 3));
      // Matches Python ones((3,15)): 3 rows x 15 cols = bridge gaps along rulings.
      var closed = new cv.Mat();
      cv.morphologyEx(bw, closed, cv.MORPH_CLOSE, k);
      var lines = new cv.Mat();
      var ph = closed.rows, pw = closed.cols;
      cv.HoughLinesP(closed, lines, 1, Math.PI / 180, 120, pyInt(Math.min(ph, pw) * 0.3), 30);
      var angles = [], weights = [];
      try {
        if (lines.rows >= 3) {
          var d = lines.data32S, i;
          for (i = 0; i < lines.rows; i++) {
            var a = Math.atan2(d[i * 4 + 3] - d[i * 4 + 1], d[i * 4 + 2] - d[i * 4]) * 180 / Math.PI;
            if (Math.abs(a) > 12.0 && Math.abs(Math.abs(a) - 180.0) > 12.0) continue;
            angles.push(a);
            weights.push(hyp(d[i * 4 + 2] - d[i * 4], d[i * 4 + 3] - d[i * 4 + 1]));
          }
        }
      } finally {
        del(work, bw, k, closed, lines);
      }
      if (angles.length < 3) return 0.0;
      var median = wmedian(angles, weights);
      if (Math.abs(median) > maxAngle || Math.abs(median) < 0.3) return 0.0;
      return median;
    } catch (e) {
      return 0.0;
    } finally {
      del(r, g, b, mv);
    }
  }

  function deskew(rgb, angle) {
    if (angle === undefined) angle = estimateSkewAngle(rgb);
    if (!angle) return rgb; // alias: already straight, no resampling
    var h = rgb.rows, w = rgb.cols;
    var M = cv.getRotationMatrix2D({ x: w / 2.0, y: h / 2.0 }, angle, 1.0);
    var out = new cv.Mat();
    cv.warpAffine(rgb, out, M, new cv.Size(w, h), cv.INTER_CUBIC, cv.BORDER_CONSTANT, white3());
    del(M);
    return out;
  }

  function residualDeskew(rgb, tolerance) {
    if (tolerance === undefined) tolerance = 0.25;
    var baseline = estimateSkewAngle(rgb);
    if (Math.abs(baseline) <= tolerance) return rgb;
    var best = rgb, bestAbs = Math.abs(baseline);
    var cands = [];
    try { cands.push(deskew(rgb, baseline)); } catch (e) { /*keep*/ }
    try {
      var warped = dewarpByRulings(rgb);
      if (warped) cands.push(warped);
    } catch (e) { /*keep*/ }
    var i;
    for (i = 0; i < cands.length; i++) {
      var candAbs;
      try { candAbs = Math.abs(estimateSkewAngle(cands[i])); }
      catch (e) { continue; }
      if (candAbs < bestAbs) {
        if (best !== rgb) del(best);
        best = cands[i]; bestAbs = candAbs;
        cands[i] = null;
      }
    }
    cands.forEach(function (c) { if (c && c !== best) del(c); });
    return best;
  }

  // ---------- trims ----------
  function trimWhiteFillBands(rgb, inkThreshold, maxFraction) {
    if (inkThreshold === undefined) inkThreshold = 240;
    if (maxFraction === undefined) maxFraction = 0.08;
    var h = rgb.rows, w = rgb.cols;
    var gray = grayOf(rgb);
    var d = gray.data, x, y, hasC, hasR;
    try {
      var maxX = pyInt(w * maxFraction), maxY = pyInt(h * maxFraction);
      var x0 = 0;
      while (x0 <= maxX) {
        hasC = false;
        for (y = 0; y < h; y++) if (d[y * w + x0] <= inkThreshold) { hasC = true; break; }
        if (hasC) break;
        x0++;
      }
      var x1 = w;
      while (x1 > w - maxX) {
        hasC = false;
        for (y = 0; y < h; y++) if (d[y * w + x1 - 1] <= inkThreshold) { hasC = true; break; }
        if (hasC) break;
        x1--;
      }
      var y0 = 0;
      while (y0 <= maxY) {
        hasR = false;
        for (x = 0; x < w; x++) if (d[y0 * w + x] <= inkThreshold) { hasR = true; break; }
        if (hasR) break;
        y0++;
      }
      var y1 = h;
      while (y1 > h - maxY) {
        hasR = false;
        for (x = 0; x < w; x++) if (d[(y1 - 1) * w + x] <= inkThreshold) { hasR = true; break; }
        if (hasR) break;
        y1--;
      }
      if (x1 - x0 < (w >> 1) || y1 - y0 < (h >> 1)) return rgb;
      if (x0 === 0 && y0 === 0 && x1 === w && y1 === h) return rgb;
      var out = rgb.roi(new cv.Rect(x0, y0, x1 - x0, y1 - y0)).clone();
      return out;
    } finally {
      del(gray);
    }
  }

  function trimSmearedTopBand(rgb, maxFraction, threshRatio) {
    if (maxFraction === undefined) maxFraction = 0.10;
    if (threshRatio === undefined) threshRatio = 0.50;
    var h = rgb.rows, w = rgb.cols;
    var gray = grayOf(rgb);
    var gx = new cv.Mat();
    cv.Sobel(gray, gx, cv.CV_32F, 1, 0, 3);
    var fd = gx.data32F, rowE = new Array(h), y, x;
    for (y = 0; y < h; y++) {
      var s = 0;
      for (x = 0; x < w; x++) s += Math.abs(fd[y * w + x]);
      rowE[y] = s / w;
    }
    var sorted = rowE.slice().sort(function (a, b) { return a - b; });
    var baseline = sorted[Math.floor(sorted.length / 2)];
    var cut = 0;
    try {
      if (baseline <= 0) return rgb;
      var cap = pyInt(h * maxFraction);
      for (y = 0; y < Math.min(cap, h); y++) {
        if (rowE[y] < threshRatio * baseline) cut = y + 1;
        else break;
      }
      if (!cut) return rgb;
      return rgb.roi(new cv.Rect(0, cut, w, h - cut)).clone();
    } finally {
      del(gray, gx);
    }
  }

  function edgeDarknessProfile(gray, thresh, smooth, winFrac) {
    if (thresh === undefined) thresh = 100;
    if (smooth === undefined) smooth = 15;
    if (winFrac === undefined) winFrac = 0.25;
    var h = gray.rows, w = gray.cols, d = gray.data;
    var win = Math.max(1, pyInt(h * winFrac)), step = Math.max(1, Math.floor(win / 2));
    var profile = new Array(w).fill(0), y0, x, y;
    for (y0 = 0; y0 < Math.max(1, h - win + 1); y0 += step) {
      for (x = 0; x < w; x++) {
        var c = 0;
        for (y = y0; y < Math.min(y0 + win, h); y++) if (d[y * w + x] < thresh) c++;
        var f = c / Math.min(win, h - y0);
        if (f > profile[x]) profile[x] = f;
      }
    }
    var ker = new Array(smooth).fill(1 / smooth);
    return convolveSame(profile, ker);
  }

  function cutDarkEdgeBands(rgb, leftThresh, rightThresh, leftCap, rightCap, smooth, minCoilW) {
    if (leftThresh === undefined) leftThresh = 0.25;
    if (rightThresh === undefined) rightThresh = 0.13;
    if (leftCap === undefined) leftCap = 0.06;
    if (rightCap === undefined) rightCap = 0.16;
    if (smooth === undefined) smooth = 15;
    if (minCoilW === undefined) minCoilW = 0.04;
    var h = rgb.rows, w = rgb.cols;
    var gray = grayOf(rgb);
    try {
      var sum = 0, d = gray.data, i;
      for (i = 0; i < d.length; i++) sum += d[i];
      if (sum / d.length > 200) return rgb;
      var prof = edgeDarknessProfile(gray);
      var x0 = 0, cap = pyInt(w * leftCap);
      while (x0 <= cap && prof[x0] > leftThresh) x0++;
      // Right side: NO cut (mirrors Python). Dense content sustains edge
      // darkness exactly like coil bands, so any automatic right cut eats
      // real text; coil cosmetics belong to binding-ring inpaint, and
      // reference outputs keep the binding visible.
      var x1 = w;
      if (x1 - x0 < (w >> 1)) return rgb;
      if (x0 === 0 && x1 === w) return rgb;
      return rgb.roi(new cv.Rect(x0, 0, x1 - x0, h)).clone();
    } finally {
      del(gray);
    }
  }

  function autoTrimMargins(rgb, left, right, top, bottom, inkThreshold,
      bandTop, bandBottom, bandLeft, bandRight) {
    if (left === undefined) left = 0.008;
    if (right === undefined) right = 0.02;
    if (top === undefined) top = 0.01;
    if (bottom === undefined) bottom = 0.02;
    if (inkThreshold === undefined) inkThreshold = 160;
    if (bandTop === undefined) bandTop = 0.12;
    if (bandBottom === undefined) bandBottom = 0.12;
    if (bandLeft === undefined) bandLeft = 0.08;
    if (bandRight === undefined) bandRight = 0.08;
    // Two tiers mirroring Python: tier 1 cuts ink-free rows/cols (small
    // caps); tier 2 cuts dark bands proven by a nearly-solid row
    // (dark-fraction >= 0.98), skipping darkish transition rows (mean <
    // 170) and the frame-edge vote. Bright-bg text can never qualify.
    var h = rgb.rows, w = rgb.cols;
    var gray = grayOf(rgb);
    var d = gray.data, x, y, v;
    try {
      var colHas = new Array(w), rowHas = new Array(h);
      var colDark = new Array(w), rowDark = new Array(h);
      var colMean = new Array(w), rowMean = new Array(h);
      var c, s, cnt;
      for (x = 0; x < w; x++) {
        s = 0; cnt = 0; c = false;
        for (y = 0; y < h; y++) { v = d[y * w + x]; s += v; if (v <= inkThreshold) { cnt++; c = true; } }
        colMean[x] = s / h; colHas[x] = c; colDark[x] = cnt / h;
      }
      for (y = 0; y < h; y++) {
        s = 0; cnt = 0; c = false;
        var base = y * w;
        for (x = 0; x < w; x++) { v = d[base + x]; s += v; if (v <= inkThreshold) { cnt++; c = true; } }
        rowMean[y] = s / w; rowHas[y] = c; rowDark[y] = cnt / w;
      }
      var x0 = 0, xCap = pyInt(w * left);
      while (x0 <= xCap && !colHas[x0]) x0++;
      var x1 = w, xCapR = pyInt(w * right);
      while (x1 > w - xCapR && !colHas[x1 - 1]) x1--;
      var y0 = 0, yCap = pyInt(h * top);
      while (y0 <= yCap && !rowHas[y0]) y0++;
      var y1 = h, yCapB = pyInt(h * bottom);
      while (y1 > h - yCapB && !rowHas[y1 - 1]) y1--;
      var j, solid, df, mn;
      // Tier 2 (dark-band walks) REMOVED to mirror Python: pre-enhance
      // darkness cannot separate dark-background headers from desk shadow
      // (it ate "Theme:"), so desk bands are removed only by the
      // post-enhance top trim, where background is white and text black.
      if (x1 - x0 < (w >> 1) || y1 - y0 < (h >> 1)) return rgb;
      if (x0 === 0 && y0 === 0 && x1 === w && y1 === h) return rgb;
      return rgb.roi(new cv.Rect(x0, y0, x1 - x0, y1 - y0)).clone();
    } finally {
      del(gray);
    }
  }

  function trimCoilMargin(rgb, zoneWidth, rowLo, rowHi, darkThresh) {
    if (zoneWidth === undefined) zoneWidth = 0.12;
    if (rowLo === undefined) rowLo = 0.10;
    if (rowHi === undefined) rowHi = 0.92;
    if (darkThresh === undefined) darkThresh = 140;
    var h = rgb.rows, w = rgb.cols;
    var gray = grayOf(rgb);
    var labels = new cv.Mat(), stats = new cv.Mat(), cents = new cv.Mat();
    try {
      var r0 = pyInt(h * rowLo), r1 = pyInt(h * rowHi);
      var zoneCols = Math.max(5, pyInt(w * zoneWidth));
      if (r1 <= r0 || zoneCols >= (w >> 1)) return rgb;
      var dark = new cv.Mat();
      cv.threshold(gray, dark, darkThresh - 1, 255, cv.THRESH_BINARY_INV);
      // NOTE: gray < darkThresh  <=>  gray <= darkThresh-1  (integer pixels).
      var n = cv.connectedComponentsWithStats(dark, labels, stats, cents, 8);
      var sd = stats.data32S;
      var minTextW = Math.max(8, pyInt(w / 40));
      var colText = new Uint8Array(w), i, x;
      for (i = 1; i < n; i++) {
        var cx = sd[i * 5], cw = sd[i * 5 + 2];
        if (cw >= minTextW) for (x = cx; x < cx + cw && x < w; x++) colText[x] = 1;
      }
      var leftCut = 0;
      for (x = 0; x < Math.min(zoneCols, w); x++) { if (colText[x]) break; leftCut = x + 1; }
      var rightCut = 0;
      for (x = w - 1; x > Math.max(w - zoneCols - 1, -1); x--) { if (colText[x]) break; rightCut = w - x; }
      if (leftCut + rightCut >= (w >> 1)) return rgb;
      if (!leftCut && !rightCut) return rgb;
      return rgb.roi(new cv.Rect(leftCut, 0, w - leftCut - rightCut, h)).clone();
    } finally {
      del(gray, labels, stats, cents);
    }
  }

  // ---------- template stub ----------
  function alignToReferenceTemplate() { return null; } // SIFT missing in WASM; no reference asset

  // ---------- binding rings ----------
  function removeBindingRings(rgb, zoneRatio, dark, minThick, minHeight, minArea) {
    if (zoneRatio === undefined) zoneRatio = 0.78;
    if (dark === undefined) dark = 70;
    if (minThick === undefined) minThick = 2.0;
    if (minHeight === undefined) minHeight = 20;
    if (minArea === undefined) minArea = 40;
    var h = rgb.rows, w = rgb.cols;
    var work = rgb.clone();
    var gray = grayOf(work);
    var darkM = new cv.Mat(), hOpen = new cv.Mat(), cand = new cv.Mat(), dist = new cv.Mat();
    var labels = new cv.Mat(), stats = new cv.Mat(), cents = new cv.Mat();
    try {
      cv.threshold(gray, darkM, dark - 1, 255, cv.THRESH_BINARY_INV);
      var kW = Math.max(25, Math.round(w / 18));
      var k = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(kW, 1));
      cv.morphologyEx(darkM, hOpen, cv.MORPH_OPEN, k);
      cv.subtract(darkM, hOpen, cand);
      cv.distanceTransform(cand, dist, cv.DIST_L2, 3);
      var fd = dist.data32F, thick = new cv.Mat(h, w, cv.CV_8U, new cv.Scalar(0));
      var td = thick.data, i;
      for (i = 0; i < fd.length; i++) td[i] = fd[i] > minThick ? 255 : 0;
      var n = cv.connectedComponentsWithStats(thick, labels, stats, cents, 8);
      var sd = stats.data32S, ld = labels.data32S;
      var xZone = pyInt(w * zoneRatio);
      var per = [];
      for (i = 1; i < n; i++) {
        var area = sd[i * 5 + 4], ch = sd[i * 5 + 3];
        if (area < minArea || ch < minHeight) continue;
        per.push({ id: i, x: sd[i * 5], cw: sd[i * 5 + 2], ch: ch, total: 0, right: 0 });
      }
      var byId = {};
      per.forEach(function (p) { byId[p.id] = p; });
      for (i = 0; i < ld.length; i++) {
        var p = byId[ld[i]];
        if (!p) continue;
        p.total++;
        if ((i % w) >= xZone) p.right++;
      }
      var mask = new cv.Mat(h, w, cv.CV_8U, new cv.Scalar(0));
      var md = mask.data;
      per.forEach(function (p) {
        if (p.right / Math.max(1, p.total) > 0.6 && (p.cw > 6 || p.ch > 6)) {
          for (var j = 0; j < ld.length; j++) if (ld[j] === p.id) md[j] = 255;
        }
      });
      var ke = cv.getStructuringElement(cv.MORPH_ELLIPSE, new cv.Size(5, 5));
      var grown = new cv.Mat();
      cv.dilate(mask, grown, ke);
      var cnt = 0, gd = grown.data;
      for (i = 0; i < gd.length; i++) if (gd[i]) cnt++;
      del(k, thick, mask, ke);
      if (cnt < 50) { del(grown); return { mat: work, removed: false }; }
      var healed = new cv.Mat();
      cv.inpaint(work, grown, healed, 5, cv.INPAINT_TELEA);
      del(work, grown);
      return { mat: healed, removed: true };
    } finally {
      del(gray, darkM, hOpen, cand, dist, labels, stats, cents);
    }
  }

  // ---------- corner / border whiten ----------
  function whitenCornerSmears(rgb, brightLo, diff, maxRatio) {
    if (brightLo === undefined) brightLo = 150;
    if (diff === undefined) diff = 18;
    if (maxRatio === undefined) maxRatio = 0.06;
    var h = rgb.rows, w = rgb.cols;
    var out = rgb.clone();
    var gray = grayOf(out);
    var blur = new cv.Mat();
    cv.GaussianBlur(gray, blur, new cv.Size(9, 9), 0);
    var bd = blur.data, gd = gray.data, od = out.data;
    var corners = [[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]], ci;
    try {
      for (ci = 0; ci < 4; ci++) {
        var sx = corners[ci][0], sy = corners[ci][1];
        if (bd[sy * w + sx] < brightLo) continue;
        var mask = new cv.Mat(h + 2, w + 2, cv.CV_8U, new cv.Scalar(0));
        var flood = blur.clone();
        try { cv.floodFill(flood, mask, new cv.Point(sx, sy), new cv.Scalar(128), new cv.Scalar(diff), new cv.Scalar(diff), cv.FLOODFILL_MASK_ONLY); }
        catch (e) { del(mask, flood); continue; }
        var md = mask.data, area = 0, dark = 0, y, x;
        for (y = 0; y < h; y++) for (x = 0; x < w; x++) {
          if (md[(y + 1) * (w + 2) + x + 1]) {
            area++;
            if (gd[y * w + x] < 160) dark++;
          }
        }
        var ratio = area / (h * w);
        if (ratio > 0.0005 && ratio < maxRatio && !dark) {
          for (y = 0; y < h; y++) for (x = 0; x < w; x++) {
            if (md[(y + 1) * (w + 2) + x + 1]) {
              od[(y * w + x) * 3] = 252; od[(y * w + x) * 3 + 1] = 252; od[(y * w + x) * 3 + 2] = 252;
            }
          }
        }
        del(mask, flood);
      }
      return out;
    } finally {
      del(gray, blur);
    }
  }

  function whitenBorderArtifacts(rgb, inkThreshold, maxDepthRatio) {
    if (inkThreshold === undefined) inkThreshold = 160;
    if (maxDepthRatio === undefined) maxDepthRatio = 0.12;
    var h = rgb.rows, w = rgb.cols;
    var out = rgb.clone();
    var gray = grayOf(out);
    var bw = new cv.Mat();
    // gray < inkThreshold  <=>  gray <= inkThreshold-1 (integer pixels).
    cv.threshold(gray, bw, inkThreshold - 1, 255, cv.THRESH_BINARY_INV);
    var contours = new cv.MatVector(), hier = new cv.Mat();
    try {
      cv.findContours(bw, contours, hier, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
      var maxD = Math.max(w, h) * maxDepthRatio, i;
      var vec = new cv.MatVector();
      try {
        for (i = 0; i < contours.size(); i++) {
          var cnt = contours.get(i);
          var r = cv.boundingRect(cnt);
          var touches = r.x <= 1 || r.y <= 1 || r.x + r.width >= w - 2 || r.y + r.height >= h - 2;
          if (touches) {
            var depth = Math.max(
              r.x <= 1 ? r.x + r.width : 0,
              r.x + r.width >= w - 2 ? w - r.x : 0,
              r.y <= 1 ? r.y + r.height : 0,
              r.y + r.height >= h - 2 ? h - r.y : 0);
            if (depth < maxD) vec.push_back(cnt);
          }
          del(cnt);
        }
        cv.drawContours(out, vec, -1, new cv.Scalar(252, 252, 252), cv.FILLED);
      } finally {
        del(vec);
      }
      return out;
    } finally {
      del(gray, bw, contours, hier);
    }
  }

  // ---------- reframe ----------
  function reframeLikeReference(rgb, opts) {
    opts = opts || {};
    var inkThr = opts.inkThreshold === undefined ? 160 : opts.inkThreshold;
    var left = opts.left === undefined ? REF_MARGIN_LEFT : opts.left;
    var right = opts.right === undefined ? REF_MARGIN_RIGHT : opts.right;
    var top = opts.top === undefined ? REF_MARGIN_TOP : opts.top;
    var bottom = opts.bottom === undefined ? REF_MARGIN_BOTTOM : opts.bottom;
    var refAspect = opts.refAspect === undefined ? REF_ASPECT_FALLBACK : opts.refAspect;
    var h = rgb.rows, w = rgb.cols;
    var gray = grayOf(rgb);
    var labels = new cv.Mat(), stats = new cv.Mat(), cents = new cv.Mat();
    try {
      var gd = gray.data, i, x, y;
      var dark = new cv.Mat(h, w, cv.CV_8U, new cv.Scalar(0));
      var dd = dark.data;
      for (i = 0; i < gd.length; i++) dd[i] = gd[i] < inkThr ? 255 : 0;
      var n = cv.connectedComponentsWithStats(dark, labels, stats, cents, 8);
      var sd = stats.data32S, ld = labels.data32S;
      var big = {};
      for (i = 1; i < n; i++) if (sd[i * 5 + 4] >= 15) big[i] = 1;
      var hasBig = Object.keys(big).length > 0;
      var y0 = h, y1 = -1, x0 = w, x1 = -1;
      for (y = 0; y < h; y++) for (x = 0; x < w; x++) {
        var on = hasBig ? !!big[ld[y * w + x]] : gd[y * w + x] < inkThr;
        if (on) {
          if (y < y0) y0 = y;
          if (y > y1) y1 = y;
          if (x < x0) x0 = x;
          if (x > x1) x1 = x;
        }
      }
      del(dark);
      if (y1 < 0) return rgb;
      y1++; x1++;
      // Fringe extension (mirrors Python exactly): reach ≤1.5%/side to the
      // extreme faint-ink (<200) pixel inside each pad window.
      var padY = Math.max(1, pyInt(h * 0.015)), padX = Math.max(1, pyInt(w * 0.015));
      var yy, xx, found, best;
      var up0 = Math.max(0, y0 - padY);
      best = -1;
      for (yy = up0; yy < y0; yy++) {
        found = false;
        for (xx = x0; xx < x1; xx++) if (gd[yy * w + xx] < 200) { found = true; break; }
        if (found) { best = yy; break; }
      }
      if (best >= 0) y0 = best;
      var dn1 = Math.min(h, y1 + padY);
      best = -1;
      for (yy = dn1 - 1; yy >= y1; yy--) {
        found = false;
        for (xx = x0; xx < x1; xx++) if (gd[yy * w + xx] < 200) { found = true; break; }
        if (found) { best = yy; break; }
      }
      if (best >= 0) y1 = Math.min(best + 1, h);
      var lf0 = Math.max(0, x0 - padX);
      best = -1;
      for (xx = lf0; xx < x0; xx++) {
        found = false;
        for (yy = y0; yy < y1; yy++) if (gd[yy * w + xx] < 200) { found = true; break; }
        if (found) { best = xx; break; }
      }
      if (best >= 0) x0 = best;
      var rt1 = Math.min(w, x1 + padX);
      best = -1;
      for (xx = rt1 - 1; xx >= x1; xx--) {
        found = false;
        for (yy = y0; yy < y1; yy++) if (gd[yy * w + xx] < 200) { found = true; break; }
        if (found) { best = xx; break; }
      }
      if (best >= 0) x1 = Math.min(best + 1, w);
      var bw = x1 - x0, bh = y1 - y0;
      if (bw < (w >> 2) || bh < (h >> 2)) return rgb;
      var minCW, minCH, canvasW, canvasH;
      if (refAspect !== null && refAspect !== undefined) {
        minCW = pyRound(bw / Math.max(1e-6, 1.0 - left - right));
        minCH = pyRound(bh / Math.max(1e-6, 1.0 - top - bottom));
        var aspectW = pyRound(minCH * refAspect);
        canvasH = minCH;
        canvasW = Math.max(minCW, aspectW);
      } else {
        canvasW = pyRound(bw / Math.max(1e-6, 1.0 - left - right));
        canvasH = pyRound(bh / Math.max(1e-6, 1.0 - top - bottom));
      }
      var ox = pyRound((canvasW - bw) / 2.0), oyTop = pyRound(top * canvasH);
      var canvas = new cv.Mat(canvasH, canvasW, cv.CV_8UC3, new cv.Scalar(255, 255, 255));
      var roi = canvas.roi(new cv.Rect(ox, oyTop, bw, bh));
      var srcRoi = rgb.roi(new cv.Rect(x0, y0, bw, bh));
      srcRoi.copyTo(roi);
      del(roi, srcRoi);
      return canvas;
    } finally {
      del(gray, labels, stats, cents);
    }
  }

  // ---------- pipeline chain (auto_scan 1043-1088, trim=true) ----------
  function swapOld(oldM, newM) { // helper: adopt newM (null-safe), delete replaced
    if (newM && newM !== oldM) { del(oldM); return newM; }
    return oldM;
  }

  function scanGeometryChain(rgb, trim) {
    if (trim === undefined) trim = true;
    var working = rgb; // caller-owned; chain deletes what it replaces
    var corners = null;
    try { corners = findDocumentContour(working); } catch (e) { corners = null; }
    if (corners) {
      try {
        var warped = warpToRectangle(working, corners);
        working = swapOld(working, warped);
      } catch (e) { /*keep*/ }
    } else {
      var dewarped = null;
      try { dewarped = dewarpByRulings(working); } catch (e) { dewarped = null; }
      var rectified = null;
      if (dewarped) { working = swapOld(working, dewarped); rectified = working; }
      else {
        try { rectified = rectifyFromRulings(working); } catch (e) { rectified = null; }
        if (rectified) { working = swapOld(working, rectified); }
        else {
          try {
            var ds = deskew(working);
            working = swapOld(working, ds);
          } catch (e) { /*keep*/ }
        }
      }
      try {
        working = swapOld(working, cutDarkEdgeBands(working));
        working = swapOld(working, trimWhiteFillBands(working));
        working = swapOld(working, trimSmearedTopBand(working));
      } catch (e) { /*keep*/ }
      if (trim) {
        try { working = swapOld(working, autoTrimMargins(working)); } catch (e) { /*keep*/ }
      }
    }
    return working;
  }

  return {
    REF_MARGIN_LEFT: REF_MARGIN_LEFT, REF_MARGIN_RIGHT: REF_MARGIN_RIGHT,
    REF_MARGIN_TOP: REF_MARGIN_TOP, REF_MARGIN_BOTTOM: REF_MARGIN_BOTTOM,
    REF_ASPECT_FALLBACK: REF_ASPECT_FALLBACK,
    orderPoints: orderPoints, findDocumentContour: findDocumentContour,
    warpToRectangle: warpToRectangle, probeGray: probeGray,
    adaptiveInkMask: adaptiveInkMask, rulingSegments: rulingSegments,
    fitLine: fitLine, dewarpByRulings: dewarpByRulings,
    rectifyFromRulings: rectifyFromRulings,
    estimateSkewAngle: estimateSkewAngle,
    estimateColorRulingTilt: estimateColorRulingTilt,
    deskew: deskew, residualDeskew: residualDeskew,
    trimWhiteFillBands: trimWhiteFillBands,
    trimSmearedTopBand: trimSmearedTopBand,
    edgeDarknessProfile: edgeDarknessProfile,
    cutDarkEdgeBands: cutDarkEdgeBands,
    alignToReferenceTemplate: alignToReferenceTemplate,
    removeBindingRings: removeBindingRings,
    whitenCornerSmears: whitenCornerSmears,
    whitenBorderArtifacts: whitenBorderArtifacts,
    reframeLikeReference: reframeLikeReference,
    trimCoilMargin: trimCoilMargin, autoTrimMargins: autoTrimMargins,
    scanGeometryChain: scanGeometryChain
  };
});
