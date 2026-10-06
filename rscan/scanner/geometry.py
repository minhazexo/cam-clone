"""Geometry stage: find the page, flatten it, straighten it.

Pipeline position: runs FIRST, on the raw photo, before photometry.

    1. corner detection + perspective warp (find_document_contour,
       warp_to_rectangle) when a closed quad exists;
    2. otherwise ruling-line based dewarp (dewarp_by_rulings) or keystone
       correction (rectify_from_rulings), which handle full-frame photos
       where the page touches the image border;
    3. otherwise a simple rotation deskew (estimate_skew_angle + deskew);
    4. residual_deskew re-checks the tilt AFTER enhancement.

Parity note: the geometry math is mirrored in
``static/js/workers/scan-geometry.js``. Ordering, thresholds and rounding
inside these functions are parity-sensitive — see ``docs/SCAN_PIPELINE.md``
before changing anything.
"""

from __future__ import annotations

import math

import cv2 as cv
import numpy as np

from rscan.scanner.preprocessing import adaptive_ink_mask, probe_gray


def order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as (top-left, top-right, bottom-right, bottom-left)."""
    pts = np.asarray(pts, dtype="float32").reshape(4, 2)
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left: smallest x+y
    rect[2] = pts[np.argmax(s)]  # bottom-right: largest x+y
    d = pts[:, 0] - pts[:, 1]    # x - y (robust to image y-down coords)
    rect[1] = pts[np.argmax(d)]  # top-right: largest x-y
    rect[3] = pts[np.argmin(d)]  # bottom-left: smallest x-y
    return rect


def find_document_contour(image: np.ndarray, min_area_ratio: float = 0.25):
    """Find the largest plausible 4-point document contour, or None.

    Returns ordered corner points (float32, shape (4, 2)) in image coords.
    """
    h, w = image.shape[:2]
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    gray = cv.GaussianBlur(gray, (5, 5), 0)
    edged = cv.Canny(gray, 30, 120)
    edged = cv.dilate(edged, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv.findContours(edged, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contours = sorted(contours, key=cv.contourArea, reverse=True)[:7]
    image_area = float(h * w)
    for cnt in contours:
        area = cv.contourArea(cnt)
        if area < min_area_ratio * image_area:
            continue
        if area > 0.995 * image_area:
            continue  # contour is the whole frame, not a page border
        peri = cv.arcLength(cnt, True)
        for eps in (0.02, 0.03, 0.05):
            approx = cv.approxPolyDP(cnt, eps * peri, True)
            if len(approx) == 4 and cv.isContourConvex(approx):
                return order_points(approx.reshape(4, 2))
    return None


def warp_to_rectangle(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """Perspective-warp the quad ``corners`` to a top-down rectangle.

    The quad is expanded ~1% about its center (clamped to the frame) first:
    contour fits routinely sit a few pixels inside the true page edge, and
    without this guard edge content is clipped for every input picture.
    """
    h, w = image.shape[:2]
    corners = np.asarray(corners, dtype="float32").reshape(4, 2)
    center = corners.mean(axis=0)
    corners = center + (corners - center) * 1.01
    corners[:, 0] = np.clip(corners[:, 0], 0, w - 1)
    corners[:, 1] = np.clip(corners[:, 1], 0, h - 1)
    (tl, tr, br, bl) = corners
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_w = max(1, int(max(width_a, width_b)))
    max_h = max(1, int(max(height_a, height_b)))
    dst = np.array(
        [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
        dtype="float32",
    )
    m = cv.getPerspectiveTransform(np.asarray(corners, dtype="float32"), dst)
    return cv.warpPerspective(image, m, (max_w, max_h), flags=cv.INTER_CUBIC)


def ruling_segments(probe: np.ndarray, max_tilt_deg: float = 12.0):
    """Long near-horizontal ruling-line segments in probe coords.

    Filters out the spiral coil / verticals (|dx| > 2|dy|), short
    handwriting fragments, and the top edge band where page-curl shadows
    form long diagonal boundaries (the failure seen on 300-DPI renders).
    Returns a list of (x1, y1, x2, y2) with x2 > x1.
    """
    probe_blur = cv.GaussianBlur(probe, (5, 5), 0)
    bw = adaptive_ink_mask(probe_blur)
    ph, pw = bw.shape[:2]
    kx = max(30, int(pw // 12))
    horizontal = cv.morphologyEx(
        bw, cv.MORPH_OPEN, cv.getStructuringElement(cv.MORPH_RECT, (kx, 1))
    )
    # Bridge small gaps (vertical dividers, ink crossings) so rulings form
    # long Hough segments even in dense handwriting areas.
    horizontal = cv.morphologyEx(
        horizontal, cv.MORPH_CLOSE,
        cv.getStructuringElement(cv.MORPH_RECT, (max(15, kx // 2), 1)),
    )
    lines = cv.HoughLinesP(
        horizontal, 1, np.pi / 180, 80,
        minLineLength=max(100, int(pw // 4)), maxLineGap=30,
    )
    if lines is None:
        return []
    out = []
    max_tilt = math.tan(math.radians(max_tilt_deg))
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        dx, dy = float(x2 - x1), float(y2 - y1)
        if dx < 0:  # normalize direction so slope sign is consistent
            dx, dy = -dx, -dy
            x1, y1, x2, y2 = x2, y2, x1, y1
        if abs(dx) < 2 * abs(dy):
            continue  # coil, verticals, noise
        if abs(dy / max(dx, 1e-6)) > max_tilt:
            continue
        cy = (y1 + y2) / 2.0
        if cy < 0.10 * ph or cy > 0.98 * ph:
            continue  # top curl-shadow band / bottom edge artifacts
        cx = (x1 + x2) / 2.0
        if cx < 0.03 * pw or cx > 0.97 * pw:
            continue  # coil / neighbor-page slivers at the sides
        out.append((float(x1), float(y1), float(x2), float(y2)))
    return out


def fit_line(segments) -> tuple[float, float]:
    """Least-squares y = m*x + c over segment endpoints. Returns (m, c)."""
    xs, ys = [], []
    for x1, y1, x2, y2 in segments:
        xs += [x1, x2]
        ys += [y1, y2]
    m, c = np.polyfit(np.asarray(xs), np.asarray(ys), 1)
    return float(m), float(c)


def dewarp_by_rulings(image: np.ndarray, n_bands: int = 6, min_bands: int = 3):
    """Curl-aware dewarp: flatten ruling lines band-by-band (y-remap).

    Notebook pages photographed up close are *curved*, not planar: top
    rulings can tilt +4deg while bottom ones tilt -5deg, so no single
    homography flattens the page. This fits one line per horizontal band
    and remaps each output row onto its band's line (center-anchored, so
    only tilt is removed, never content shifted). Returns warped image or
    None when fewer than ``min_bands`` bands carry usable rulings.
    """
    h, w = image.shape[:2]
    probe, _ = probe_gray(image)
    ph, pw = probe.shape[:2]
    segments = ruling_segments(probe)
    y_lo, y_hi = 0.06 * ph, 0.98 * ph
    edges = np.linspace(y_lo, y_hi, n_bands + 1)
    slopes, centers_y = [], []
    for i in range(n_bands):
        # Overlapping bands (25% each side) catch lines on boundaries and
        # pool scarce header rulings with neighbors.
        lo = edges[i] - 0.25 * (edges[i + 1] - edges[i])
        hi = edges[i + 1] + 0.25 * (edges[i + 1] - edges[i])
        band = [s for s in segments if lo <= (s[1] + s[3]) / 2.0 < hi]
        if len(band) < 2:
            slopes.append(None)
            centers_y.append(float((edges[i] + edges[i + 1]) / 2.0))
            continue
        xs = [p for s in band for p in (s[0], s[2])]
        if max(xs) - min(xs) < 0.4 * pw:
            slopes.append(None)
            centers_y.append(float((edges[i] + edges[i + 1]) / 2.0))
            continue
        m, _ = fit_line(band)
        if abs(m) > math.tan(math.radians(12.0)):
            slopes.append(None)
        else:
            slopes.append(float(m))
        centers_y.append(float((edges[i] + edges[i + 1]) / 2.0))
    good = [m for m in slopes if m is not None]
    if len(good) < min_bands:
        return None
    # Fill missing bands by nearest-good interpolation.
    filled = []
    for i, m in enumerate(slopes):
        if m is not None:
            filled.append(m)
            continue
        prev = next((slopes[j] for j in range(i - 1, -1, -1)
                     if slopes[j] is not None), None)
        nxt = next((slopes[j] for j in range(i + 1, len(slopes))
                    if slopes[j] is not None), None)
        if prev is not None and nxt is not None:
            filled.append((prev + nxt) / 2.0)
        else:
            filled.append(prev if prev is not None else nxt)
    # Smooth across bands to avoid kinks.
    arr = np.asarray(filled, dtype=np.float64)
    ker = np.array([0.25, 0.5, 0.25])
    arr = np.convolve(np.pad(arr, 1, mode="edge"), ker, mode="valid")
    # Per-row slope by interpolating band centers, then remap.
    rows = np.arange(h, dtype=np.float64)
    probe_rows = rows * (ph / h)
    m_of_y = np.interp(probe_rows,
                       np.asarray(centers_y) * 1.0, arr,
                       left=arr[0], right=arr[-1])
    cx = w / 2.0
    xs = np.arange(w, dtype=np.float32)
    map_x = np.tile(xs, (h, 1))
    # NOTE: slope is scale-invariant (dy/dx); center in full-res coords.
    map_y = (rows[:, None]
             + m_of_y[:, None]
             * (np.arange(w, dtype=np.float64)[None, :] - cx)).astype(np.float32)
    white = (255, 255, 255) if image.ndim == 3 and image.shape[2] == 3 else 255
    return cv.remap(image, map_x.astype(np.float32), map_y,
                    interpolation=cv.INTER_CUBIC,
                    borderMode=cv.BORDER_CONSTANT, borderValue=white)


def rectify_from_rulings(image: np.ndarray, max_tilt_deg: float = 12.0):
    """Keystone-correct using notebook ruling lines. Returns warped or None.

    Fits one line through the top-band rulings and one through the
    bottom-band rulings (least squares over Hough segments), then maps the
    resulting trapezoid to an axis-aligned rectangle. Fixes both global
    rotation and the top-vs-bottom tilt difference (keystone) that a
    single rotation cannot. Returns None when evidence is insufficient.
    """
    h, w = image.shape[:2]
    probe, scale = probe_gray(image)
    ph, pw = probe.shape[:2]
    segments = ruling_segments(probe, max_tilt_deg)
    top = [s for s in segments if (s[1] + s[3]) / 2.0 < 0.45 * ph]
    bottom = [s for s in segments if (s[1] + s[3]) / 2.0 > 0.55 * ph]
    if len(top) < 2 or len(bottom) < 2:
        return None
    # Each band must span most of the page width to anchor the fit.
    for band in (top, bottom):
        xs = [p for s in band for p in (s[0], s[2])]
        if max(xs) - min(xs) < 0.5 * pw:
            return None
    mt, ct = fit_line(top)
    mb, cb = fit_line(bottom)
    # Sanity: gentle slopes only. Opposite signs are fine -- that is the
    # keystone itself (world-parallel rulings converging to a vanishing
    # point); the trapezoid-to-rectangle warp below is what removes it.
    max_m = math.tan(math.radians(max_tilt_deg))
    if abs(mt) > max_m or abs(mb) > max_m:
        return None
    if abs(mt - mb) > math.tan(math.radians(15.0)):
        return None
    inv = 1.0 / scale
    src = np.array([
        [0.0, ct * inv],
        [(pw - 1) * inv, (mt * (pw - 1) + ct) * inv],
        [(pw - 1) * inv, (mb * (pw - 1) + cb) * inv],
        [0.0, cb * inv],
    ], dtype="float32")
    yt = float((src[0][1] + src[1][1]) / 2.0)
    yb = float((src[2][1] + src[3][1]) / 2.0)
    if yb - yt < 0.25 * h:
        return None
    yt = float(np.clip(yt, 0, h - 1))
    yb = float(np.clip(yb, 0, h - 1))
    dst = np.array([
        [0.0, yt], [float(w - 1), yt], [float(w - 1), yb], [0.0, yb],
    ], dtype="float32")
    try:
        m = cv.getPerspectiveTransform(src, dst)
    except Exception:
        return None
    white = (255, 255, 255) if image.ndim == 3 and image.shape[2] == 3 else 255
    return cv.warpPerspective(
        image, m, (w, h), flags=cv.INTER_CUBIC,
        borderMode=cv.BORDER_CONSTANT, borderValue=white,
    )


def estimate_color_ruling_tilt(image: np.ndarray, max_angle: float = 10.0) -> float:
    """Tilt of colored ruling lines (red/pink notebook margins) in degrees.

    Handwriting ink is near-gray (R≈G≈B) so the R−G channel erases text and
    isolates colored rulings that are invisible to luminance detectors.
    Length-weighted median of long near-horizontal segments; 0.0 when
    nothing reliable is found. Same OpenCV rotation sign as
    ``estimate_skew_angle`` (positive = counter-clockwise correction).
    """
    try:
        b, g, r = cv.split(image.astype(np.int16)) if image.ndim == 3 else (None,) * 3
        if b is None:
            return 0.0
        pink = np.clip(r - g, 0, 255).astype(np.uint8)
        h, w = pink.shape[:2]
        scale = 1000.0 / w if w > 1000 else 1.0
        if scale < 1.0:
            pink = cv.resize(pink, None, fx=scale, fy=scale,
                             interpolation=cv.INTER_AREA)
        _, bw = cv.threshold(pink, 25, 255, cv.THRESH_BINARY)
        bw = cv.morphologyEx(bw, cv.MORPH_CLOSE, np.ones((3, 15), np.uint8))
        ph, pw = bw.shape[:2]
        lines = cv.HoughLinesP(bw, 1, np.pi / 180, threshold=120,
                               minLineLength=int(min(ph, pw) * 0.3),
                               maxLineGap=30)
        if lines is None or len(lines) < 3:
            return 0.0
        angles, weights = [], []
        for l in lines:
            x1, y1, x2, y2 = (int(v) for v in l)
            a = math.degrees(math.atan2(y2 - y1, x2 - x1))
            if abs(a) > 12.0 and abs(abs(a) - 180.0) > 12.0:
                continue  # not near-horizontal; diagonals lie
            length = math.hypot(x2 - x1, y2 - y1)
            angles.append(a)
            weights.append(length)
        if len(angles) < 3:
            return 0.0
        order = np.argsort(angles)
        angles = np.asarray(angles, dtype=float)[order]
        weights = np.asarray(weights, dtype=float)[order]
        cumulative = np.cumsum(weights)
        median = float(angles[np.searchsorted(cumulative, cumulative[-1] / 2.0)])
        if abs(median) > max_angle:
            return 0.0
        if abs(median) < 0.3:
            return 0.0  # already straight; avoid needless resampling
        return median
    except Exception:
        return 0.0


def estimate_skew_angle(image: np.ndarray, max_angle: float = 15.0) -> float:
    """Estimate dominant text-line tilt in degrees (OpenCV rotation sign).

    Positive means counter-clockwise correction. Falls back to colored
    ruling lines (pink/red notebook margins) when luminance finds nothing —
    those are invisible in grayscale but often carry the page tilt.
    Returns 0.0 when no reliable lines are found or the angle is
    implausibly large.
    """
    probe, _ = probe_gray(image)
    segments = ruling_segments(probe, max_tilt_deg=max_angle)
    if len(segments) >= 5:
        angles, weights = [], []
        for x1, y1, x2, y2 in segments:
            dx, dy = x2 - x1, y2 - y1
            angles.append(math.degrees(math.atan2(dy, dx)))
            weights.append(math.hypot(dx, dy))
        # Length-weighted median: long ruling lines outvote short fragments.
        order = np.argsort(angles)
        angles = np.asarray(angles, dtype=float)[order]
        weights = np.asarray(weights, dtype=float)[order]
        cumulative = np.cumsum(weights)
        median = float(angles[np.searchsorted(cumulative, cumulative[-1] / 2.0)])
        if abs(median) <= max_angle and abs(median) >= 0.3:
            return median
    return estimate_color_ruling_tilt(image, max_angle=min(max_angle, 10.0))


def deskew(image: np.ndarray, angle: float | None = None) -> np.ndarray:
    """Rotate image to make text lines horizontal."""
    if angle is None:
        angle = estimate_skew_angle(image)
    if not angle:
        return image
    h, w = image.shape[:2]
    m = cv.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    white = (255, 255, 255) if image.ndim == 3 and image.shape[2] == 3 else 255
    return cv.warpAffine(
        image, m, (w, h), flags=cv.INTER_CUBIC,
        borderMode=cv.BORDER_CONSTANT, borderValue=white,
    )


def residual_deskew(image: np.ndarray, tolerance: float = 0.25) -> np.ndarray:
    """Flatten ruling lines that only became visible after enhancement.

    Geometry correction runs *before* enhancement, when faint notebook
    rulings are still too low-contrast for the line detector, so a curl
    of ~1deg can survive into the enhanced image. This re-measures the
    tilt there and keeps whichever straightening (band-wise dewarp or a
    simple rotation) actually reduces it. Returns the input untouched
    when it is already straight or no candidate helps.
    """
    baseline = estimate_skew_angle(image)
    if abs(baseline) <= tolerance:
        return image
    best, best_abs = image, abs(baseline)
    candidates = [deskew(image, baseline)]
    try:
        warped = dewarp_by_rulings(image)
    except Exception:
        warped = None
    if warped is not None:
        candidates.append(warped)
    for cand in candidates:
        try:
            cand_abs = abs(estimate_skew_angle(cand))
        except Exception:
            continue
        if cand_abs < best_abs:
            best, best_abs = cand, cand_abs
    return best


__all__ = [
    "order_points",
    "find_document_contour",
    "warp_to_rectangle",
    "ruling_segments",
    "fit_line",
    "dewarp_by_rulings",
    "rectify_from_rulings",
    "estimate_color_ruling_tilt",
    "estimate_skew_angle",
    "deskew",
    "residual_deskew",
]
