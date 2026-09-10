"""Reference-quality photo scanner.

Converts phone photos of documents (including photos embedded in PDFs)
to the clean, flat, white-background look of ``wiki_images/reference.png``.

Pipeline per page/photo (BGR -> BGR):
  1. document geometry: try 4-point perspective warp; fallback to
     text-line deskew + margin trim (handles full-frame photos where the
     page touches the image border and no closed quad exists).
  2. photometric enhance (improved GCMODE): background estimation with a
     large box blur, high-pass flatten, white-point stretch to pure white,
     black-point stretch for text contrast. Preserves ink color
     (e.g. blue headings) like the reference.
  3. light denoise that does not blur text.

Pure OpenCV + NumPy. No hardcoded paths, no manual thresholds required
(auto white/black points with sane fallbacks to the original 127/66).
"""

import math

import cv2 as cv
import numpy as np

# Defaults matching the original RScan GCMODE, kept for compatibility.
DEFAULT_WHITE_POINT = 127
DEFAULT_BLACK_POINT = 66
DEFAULT_BLACK_POINT2 = 68  # second black stretch: pushes ink cores dark like reference
DEFAULT_SATURATE = 1.25   # slight RGB chroma boost to preserve colored ink
DEFAULT_KSIZE_DIVISOR = 8  # ksize = min(h, w) // divisor (made odd)


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def order_points(pts):
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


def find_document_contour(image, min_area_ratio=0.25):
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


def warp_to_rectangle(image, corners):
    """Perspective-warp the quad ``corners`` to a top-down rectangle."""
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


def _probe_gray(image, target_width=1000):
    """Grayscale probe scaled to ``target_width`` + the scale factor.

    Scale-invariant estimation: phone photos (~480px) and 300-DPI PDF
    renders (2000px+) are analyzed at the same resolution; fitted
    coordinates are divided by ``scale`` to map back to full resolution.
    """
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    if gray.shape[1] > target_width:
        scale = target_width / float(gray.shape[1])
        probe = cv.resize(gray, None, fx=scale, fy=scale,
                          interpolation=cv.INTER_AREA)
        return probe, scale
    return gray, 1.0


def _adaptive_ink_mask(probe_blur):
    """Ink/lines mask robust to uneven lighting (adaptive, inverted)."""
    pw = probe_blur.shape[1]
    block = max(21, int(pw // 15))
    if block % 2 == 0:
        block += 1
    block = min(block, 101)
    return cv.adaptiveThreshold(
        probe_blur, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv.THRESH_BINARY_INV, block, 7,
    )


def _ruling_segments(probe, max_tilt_deg=12.0):
    """Long near-horizontal ruling-line segments in probe coords.

    Filters out the spiral coil / verticals (|dx| > 2|dy|), short
    handwriting fragments, and the top edge band where page-curl shadows
    form long diagonal boundaries (the failure seen on 300-DPI renders).
    Returns a list of (x1, y1, x2, y2) with x2 > x1.
    """
    probe_blur = cv.GaussianBlur(probe, (5, 5), 0)
    # Adaptive (not Otsu): global thresholds merge dense handwriting into
    # blobs under uneven phone-photo lighting; adaptive keeps thin rulings.
    bw = _adaptive_ink_mask(probe_blur)
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


def _fit_line(segments):
    """Least-squares y = m*x + c over segment endpoints. Returns (m, c)."""
    xs, ys = [], []
    for x1, y1, x2, y2 in segments:
        xs += [x1, x2]
        ys += [y1, y2]
    m, c = np.polyfit(np.asarray(xs), np.asarray(ys), 1)
    return float(m), float(c)


def dewarp_by_rulings(image, n_bands=6, min_bands=3):
    """Curl-aware dewarp: flatten ruling lines band-by-band (y-remap).

    Notebook pages photographed up close are *curved*, not planar: top
    rulings can tilt +4deg while bottom ones tilt -5deg, so no single
    homography flattens the page. This fits one line per horizontal band
    and remaps each output row onto its band's line (center-anchored, so
    only tilt is removed, never content shifted). Returns warped image or
    None when fewer than ``min_bands`` bands carry usable rulings.
    """
    h, w = image.shape[:2]
    probe, _ = _probe_gray(image)
    ph, pw = probe.shape[:2]
    segments = _ruling_segments(probe)
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
        m, _ = _fit_line(band)
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


def rectify_from_rulings(image, max_tilt_deg=12.0):
    """Keystone-correct using notebook ruling lines. Returns warped or None.

    Fits one line through the top-band rulings and one through the
    bottom-band rulings (least squares over Hough segments), then maps the
    resulting trapezoid to an axis-aligned rectangle. Fixes both global
    rotation and the top-vs-bottom tilt difference (keystone) that a
    single rotation cannot. Returns None when evidence is insufficient.
    """
    h, w = image.shape[:2]
    probe, scale = _probe_gray(image)
    ph, pw = probe.shape[:2]
    segments = _ruling_segments(probe, max_tilt_deg)
    top = [s for s in segments if (s[1] + s[3]) / 2.0 < 0.45 * ph]
    bottom = [s for s in segments if (s[1] + s[3]) / 2.0 > 0.55 * ph]
    if len(top) < 2 or len(bottom) < 2:
        return None
    # Each band must span most of the page width to anchor the fit.
    for band in (top, bottom):
        xs = [p for s in band for p in (s[0], s[2])]
        if max(xs) - min(xs) < 0.5 * pw:
            return None
    mt, ct = _fit_line(top)
    mb, cb = _fit_line(bottom)
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


def estimate_skew_angle(image, max_angle=15.0):
    """Estimate dominant text-line tilt in degrees (OpenCV rotation sign).

    Positive means counter-clockwise correction. Returns 0.0 when no
    reliable lines are found or the angle is implausibly large.
    """
    probe, _ = _probe_gray(image)
    segments = _ruling_segments(probe, max_tilt_deg=max_angle)
    if len(segments) < 5:
        return 0.0
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
    if abs(median) > max_angle:
        return 0.0
    if abs(median) < 0.3:
        return 0.0  # already straight; avoid needless resampling
    return median


def deskew(image, angle=None):
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


def trim_white_fill_bands(image, ink_threshold=240, max_fraction=0.08):
    """Cut pure-white warp-fill bands at the edges (post-rectify/deskew).

    Drops leading/trailing rows/cols containing no ink pixel
    (min channel <= ``ink_threshold``), capped at ``max_fraction`` per
    side so real paper margins are never eaten.
    """
    h, w = image.shape[:2]
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY) if image.ndim == 3 else image
    has_ink_col = (gray.min(axis=0) <= ink_threshold)
    has_ink_row = (gray.min(axis=1) <= ink_threshold)
    max_x = int(w * max_fraction)
    max_y = int(h * max_fraction)
    x0 = 0
    while x0 <= max_x and not has_ink_col[x0]:
        x0 += 1
    x1 = w
    while x1 > w - max_x and not has_ink_col[x1 - 1]:
        x1 -= 1
    y0 = 0
    while y0 <= max_y and not has_ink_row[y0]:
        y0 += 1
    y1 = h
    while y1 > h - max_y and not has_ink_row[y1 - 1]:
        y1 -= 1
    if x1 - x0 < w // 2 or y1 - y0 < h // 2:
        return image
    return image[y0:y1, x0:x1]


def trim_smeared_top_band(image, max_fraction=0.06, thresh_ratio=0.30):
    """Cut a warp-smeared band at the top edge, if present.

    Perspective extrapolation can stretch near-edge content into a blurry
    strip. Detect rows with almost no edge energy and drop them (capped at
    ``max_fraction`` of height). No-op on already-clean pages.
    """
    h, w = image.shape[:2]
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY) if image.ndim == 3 else image
    grad = cv.Sobel(gray, cv.CV_32F, 1, 0, ksize=3)
    row_energy = np.abs(grad).mean(axis=1)
    baseline = float(np.median(row_energy))
    if baseline <= 0:
        return image
    cap = int(h * max_fraction)
    cut = 0
    for y in range(min(cap, h)):
        if row_energy[y] < thresh_ratio * baseline:
            cut = y + 1
        else:
            break
    return image[cut:, :] if cut else image


def cut_dark_edge_bands(image, left_thresh=0.25, right_thresh=0.13,
                        left_cap=0.06, right_cap=0.16, smooth=15,
                        min_coil_width_ratio=0.04):
    """Cut page-gap shadow (left) and spiral-coil band (right) adaptively.

    Operates on the rectified but NOT yet enhanced photo. Already-clean
    scans (bright overall) are returned untouched. Left: the gap shadow is
    *solid* dark, so a high sustained threshold never touches text. Right:
    only a *wide* sustained dark run (coil rings span 10%+ of the width;
    text strokes and punched-hole dots do not) is cut. No-op if nothing
    qualifies.
    """
    h, w = image.shape[:2]
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY) if image.ndim == 3 else image
    if float(gray.mean()) > 200:
        return image  # already a clean scan; nothing to cut
    band = gray[int(h * 0.30):int(h * 0.95), :] < 100
    frac = band.mean(axis=0).astype(np.float64)
    kernel = np.ones(smooth) / float(smooth)
    smooth_frac = np.convolve(frac, kernel, mode="same")
    x0 = 0
    while x0 <= int(w * left_cap) and smooth_frac[x0] > left_thresh:
        x0 += 1
    x1 = w
    run_start = w
    while run_start > w - int(w * right_cap) and smooth_frac[run_start - 1] > right_thresh:
        run_start -= 1
    if (w - run_start) >= max(8, int(w * min_coil_width_ratio)):
        x1 = run_start
    if x1 - x0 < w // 2:
        return image
    return image[:, x0:x1]


# Reference framing measured from wiki_images/reference.png:
# content ink bbox occupies cols 6.9%-92.9%, rows 3.8%-95.6%.
REF_MARGIN_LEFT = 0.069
REF_MARGIN_RIGHT = 0.071
REF_MARGIN_TOP = 0.038
REF_MARGIN_BOTTOM = 0.044


def remove_binding_rings(image, zone_ratio=0.78, dark=70, min_thick=2.0,
                         min_height=20, min_area=40):
    """Erase spiral-binding rings overlapping the page (inpaint with paper).

    Rings are the only structures that are simultaneously very dark, thick
    (distance-transform radius), tall, non-horizontal, and living in the
    right edge zone. Horizontal rulings are subtracted first; thin ink
    strokes never qualify by thickness/height. Operates on the *enhanced*
    image where rings are pure black on white paper. Returns (image,
    removed_bool).
    """
    work = image.copy()
    h, w = work.shape[:2]
    gray = cv.cvtColor(work, cv.COLOR_BGR2GRAY) if work.ndim == 3 else work
    dark_mask = (gray < dark).astype(np.uint8) * 255
    # Subtract long horizontal rulings (rings are diagonal).
    h_open = cv.morphologyEx(
        dark_mask, cv.MORPH_OPEN,
        cv.getStructuringElement(cv.MORPH_RECT, (max(25, w // 18), 1)))
    cand = cv.subtract(dark_mask, h_open)
    # Thickness gate: strokes are ~1px radius, rings ~2.5px+.
    dist = cv.distanceTransform(cand, cv.DIST_L2, 3)
    thick = (dist > min_thick).astype(np.uint8) * 255
    # Keep only connected blobs that live mostly in the right zone.
    n, lab, stats, _ = cv.connectedComponentsWithStats(thick, 8)
    x_zone = int(w * zone_ratio)
    mask = np.zeros_like(thick)
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if area < min_area or ch < min_height:
            continue
        ys, xs = np.where(lab == i)
        frac_right = float((xs >= x_zone).mean())
        if frac_right > 0.6 and (cw > 6 or ch > 6):
            mask[lab == i] = 255
    # Grow slightly into anti-aliased ring edges, then inpaint.
    mask = cv.dilate(mask, cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5)))
    if int((mask > 0).sum()) < 50:
        return work, False
    if work.ndim == 3:
        work = cv.inpaint(work, mask, 5, cv.INPAINT_TELEA)
    else:
        work = cv.inpaint(work, mask, 5, cv.INPAINT_TELEA)
    return work, True


def whiten_corner_smears(image, bright_lo=150, diff=18, max_ratio=0.06):
    """Whiten out-of-focus neighbor-page smears in the corners.

    On the enhanced image these are smooth bright-gray regions touching a
    corner (no dark strokes inside). Flood-fill from each corner through
    bright, low-contrast pixels; fill white only when the region is small
    and stroke-free.
    """
    out = image.copy()
    h, w = out.shape[:2]
    gray = cv.cvtColor(out, cv.COLOR_BGR2GRAY) if out.ndim == 3 else out
    blur = cv.GaussianBlur(gray, (9, 9), 0)
    for sx, sy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if int(blur[sy, sx]) < bright_lo:
            continue
        mask = np.zeros((h + 2, w + 2), np.uint8)
        try:
            _, flood, _, _ = cv.floodFill(blur.copy(), mask, (sx, sy), 128,
                                          (diff,), (diff,),
                                          cv.FLOODFILL_MASK_ONLY)
        except Exception:
            continue
        region = flood[1:-1, 1:-1] > 0
        area_ratio = float(region.mean())
        if not 0.0005 < area_ratio < max_ratio:
            continue
        if int((gray[region] < 160).sum()) > 0:
            continue  # real strokes inside; not a smear
        out[region] = 252  # match paper tone, not pure white
    return out


def whiten_border_artifacts(image, ink_threshold=160, max_depth_ratio=0.12):
    """Whiten artifact specks touching the outer image border.

    After reference re-framing, margins are pure white by construction, so
    any ink component touching the border inside them (corner shadow wedge,
    coil remnant, edge smear) is an artifact. Components reaching deeper
    than ``max_depth_ratio`` are kept (real content). Operates in place on
    a copy and returns it.
    """
    out = image.copy()
    h, w = out.shape[:2]
    gray = cv.cvtColor(out, cv.COLOR_BGR2GRAY) if out.ndim == 3 else out
    _, bw = cv.threshold(gray, ink_threshold, 255, cv.THRESH_BINARY_INV)
    contours, _ = cv.findContours(bw, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    max_dx, max_dy = w * max_depth_ratio, h * max_depth_ratio
    for cnt in contours:
        x, y, cw, ch = cv.boundingRect(cnt)
        touches = (x <= 1) or (y <= 1) or (x + cw >= w - 2) or (y + ch >= h - 2)
        if not touches:
            continue
        # depth = how far the component reaches inward from the border
        depth = max(
            (x + cw) if x <= 1 else 0,
            (w - x) if x + cw >= w - 2 else 0,
            (y + ch) if y <= 1 else 0,
            (h - y) if y + ch >= h - 2 else 0,
        )
        if depth < max(max_dx, max_dy):
            cv.drawContours(out, [cnt], -1, (252, 252, 252), cv.FILLED)
    return out


def reframe_like_reference(image, ink_threshold=160,
                           left=REF_MARGIN_LEFT, right=REF_MARGIN_RIGHT,
                           top=REF_MARGIN_TOP, bottom=REF_MARGIN_BOTTOM):
    """Re-frame a scanned page to the reference's edge/placement quality.

    Takes the ink bounding box (faint watermarks above ``ink_threshold``
    stay out of the box) and centers it on a white canvas with the same
    symmetric margins as reference.png. Edges become pure white; nothing
    is distorted (aspect follows the content).
    """
    h, w = image.shape[:2]
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY) if image.ndim == 3 else image
    ink = gray < ink_threshold
    if not ink.any():
        return image
    # Remove isolated small noise: keep only connected components with
    # area >= 15 pixels (a single character stroke is 50+ px).
    n_labels, labels, stats, _ = cv.connectedComponentsWithStats(
        ink.astype('uint8'), 8)
    clean = np.zeros_like(ink)
    for i in range(1, n_labels):
        if stats[i, cv.CC_STAT_AREA] >= 15:
            clean[labels == i] = True
    if not clean.any():
        clean = ink
    rows = np.where(clean.any(axis=1))[0]
    cols = np.where(clean.any(axis=0))[0]
    y0, y1 = int(rows.min()), int(rows.max()) + 1
    x0, x1 = int(cols.min()), int(cols.max()) + 1
    bw, bh = x1 - x0, y1 - y0
    if bw < w // 4 or bh < h // 4:
        return image  # degenerate detection; keep input
    canvas_w = int(round(bw / max(1e-6, 1.0 - left - right)))
    canvas_h = int(round(bh / max(1e-6, 1.0 - top - bottom)))
    canvas_w = max(canvas_w, w)
    canvas_h = max(canvas_h, h)
    ox = int(round((canvas_w - bw) / 2.0))
    oy_top = int(round(top * canvas_h))
    PAPER_GRAY = 255  # let HPF provide natural paper tone in content area
    if image.ndim == 3:
        canvas = np.full((canvas_h, canvas_w, 3), PAPER_GRAY, dtype=np.uint8)
        canvas[oy_top:oy_top + bh, ox:ox + bw] = image[y0:y1, x0:x1]
    else:
        canvas = np.full((canvas_h, canvas_w), PAPER_GRAY, dtype=np.uint8)
        canvas[oy_top:oy_top + bh, ox:ox + bw] = image[y0:y1, x0:x1]
    return canvas


def trim_coil_margin(image, zone_width=0.12, row_lo=0.10, row_hi=0.92,
                     dark_thresh=140):
    """Cut sparse spiral-coil marks from left/right margins of enhanced image.

    Strategy: in the margin zone, cluster dark pixels into connected
    components.  Coil marks are small isolated blobs; text strokes form
    large connected groups.  Trims from each edge inward until encountering
    a component wider than ``min_text_width`` pixels.
    """
    h, w = image.shape[:2]
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY) if image.ndim == 3 else image
    r0, r1 = int(h * row_lo), int(h * row_hi)
    zone_cols = max(5, int(w * zone_width))
    if r1 <= r0 or zone_cols >= w // 2:
        return image

    strip = gray[r0:r1, :]
    dark = (strip < dark_thresh).astype('uint8') * 255

    # Connected components on the dark mask
    n_labels, labels, stats, _ = cv.connectedComponentsWithStats(dark, 8)
    # Build per-column "has large component" flag
    min_text_width = max(8, w // 40)  # text strokes span >= this many pixels
    col_has_text = np.zeros(w, dtype=bool)
    for i in range(1, n_labels):
        x, y, cw, ch_c, area = stats[i]
        if cw >= min_text_width:
            col_has_text[x:x + cw] = True

    # Left edge: trim columns without text
    left_cut = 0
    for c in range(min(zone_cols, w)):
        if col_has_text[c]:
            break
        left_cut = c + 1

    # Right edge: trim columns without text
    right_cut = 0
    for c in range(w - 1, max(w - zone_cols - 1, -1), -1):
        if col_has_text[c]:
            break
        right_cut = w - c

    if left_cut + right_cut >= w // 2:
        return image
    x1 = w - right_cut if right_cut else w
    return image[:, left_cut:x1]


def auto_trim_margins(image, left=0.008, right=0.02, top=0.01, bottom=0.02):
    """Micro-border trim. Heavy lifting (shadow/coil) is done adaptively by
    cut_dark_edge_bands; defaults stay small so text is never eaten."""
    h, w = image.shape[:2]
    x0 = int(w * left)
    x1 = int(w * (1.0 - right))
    y0 = int(h * top)
    y1 = int(h * (1.0 - bottom))
    if x1 - x0 < w // 2 or y1 - y0 < h // 2:
        return image
    return image[y0:y1, x0:x1]


# ---------------------------------------------------------------------------
# photometric enhance (improved GCMODE, reference look)
# ---------------------------------------------------------------------------

def _odd_kernel(min_dim, divisor=DEFAULT_KSIZE_DIVISOR, minimum=21, maximum=101):
    ksize = max(minimum, int(min_dim // divisor))
    ksize = min(maximum, ksize)
    if ksize % 2 == 0:
        ksize += 1
    return ksize


def high_pass_flatten(image, ksize=None):
    """Flatten uneven lighting: img - background + 127, per channel."""
    if ksize is None:
        h, w = image.shape[:2]
        ksize = _odd_kernel(min(h, w))
    if ksize % 2 == 0:
        ksize += 1
    kernel = np.ones((ksize, ksize), np.float32) / float(ksize * ksize)
    background = cv.filter2D(image, -1, kernel)
    flat = (
        image.astype(np.float32) - background.astype(np.float32) + 127.0
    )
    return np.clip(flat, 0, 255).astype(np.uint8)


def white_point_stretch(image, white_point=DEFAULT_WHITE_POINT):
    """TRUNC highlights above white_point, then stretch [0, wp] -> [0, 255]."""
    white_point = float(np.clip(white_point, 1, 255))
    _, truncated = cv.threshold(image, white_point, 255, cv.THRESH_TRUNC)
    return np.clip(
        truncated.astype(np.float32) * (255.0 / white_point), 0, 255
    ).astype(np.uint8)


def black_point_stretch(image, black_point=DEFAULT_BLACK_POINT):
    """Push shadows to black: (img - bp) * 255 / (255 - bp)."""
    black_point = float(np.clip(black_point, 0, 254))
    if black_point <= 0:
        return image
    return np.clip(
        (image.astype(np.float32) - black_point)
        * (255.0 / (255.0 - black_point)),
        0,
        255,
    ).astype(np.uint8)


def auto_black_point(image, pct=8.0):
    """Pick a black point from the dark-text tail of the histogram.

    After white-point stretching the background is ~255. Reference scans
    (CamScanner) carry deep blacks through ~5-10% of pixels, so the point
    tracks a higher percentile than just the darkest cores; clamped so
    blank pages cannot blow out.
    """
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    value = float(np.percentile(gray, pct))
    return float(np.clip(value, 10, 120))


def enhance_reference_look(image, ksize=None, white_point=None, black_point=None,
                           black_point2=None, saturate=DEFAULT_SATURATE):
    """Photometric pass that reproduces the reference's white background.

    Per-channel mirror of the original RScan GCMODE: HPF flattens the
    illumination, highlights are truncated/stretched to pure white, then a
    black stretch (done twice) pushes ink cores near-black. Runs per BGR
    channel so colored ink (blue headings, colored markings) keeps its hue,
    which is why the reference.png still shows color. Optional saturation
    boost amplifies faint colored ink the same way the reference shows it.
    """
    ksize = 101 if ksize is None else ksize
    flat = high_pass_flatten(image, ksize=ksize)
    if flat.ndim == 3 and abs(saturate - 1.0) > 1e-6:
        b, g, r = cv.split(flat.astype(np.float32))
        lum = (r + g + b) / 3.0
        flat = cv.merge([lum + (b - lum) * saturate,
                         lum + (g - lum) * saturate,
                         lum + (r - lum) * saturate])
    wp = DEFAULT_WHITE_POINT if white_point is None else float(white_point)
    _, truncated = cv.threshold(flat, wp, 255, cv.THRESH_TRUNC)
    out = np.clip(truncated.astype(np.float32) * (255.0 / wp), 0, 255)
    bp = DEFAULT_BLACK_POINT if black_point is None else float(black_point)
    out = np.clip((out - bp) * (255.0 / (255.0 - bp)), 0, 255)
    bp2 = DEFAULT_BLACK_POINT2 if black_point2 is None else float(black_point2)
    out = np.clip((out - bp2) * (255.0 / (255.0 - bp2)), 0, 255)
    _, out = cv.threshold(out, 0, 255, cv.THRESH_TOZERO)
    return out.astype(np.uint8)


# ---------------------------------------------------------------------------
# full pipeline
# ---------------------------------------------------------------------------

def scan_photo_to_reference(image, ksize=None, white_point=None,
                            black_point=None, trim=True, reframe=True,
                            output_scale=2.0):
    """Convert one phone photo (BGR) to reference-quality scan (BGR).

    Geometry first (warp or deskew+trim), photometry second, reference
    framing last. ``output_scale`` upscales the final scan (reference.png
    is ~2x the wiki photo's pixels). Never raises on degenerate input:
    falls back to photometry-only.
    """
    if image is None or getattr(image, "size", 0) == 0:
        raise ValueError("empty input image")
    working = image
    try:
        corners = find_document_contour(working)
    except Exception:
        corners = None
    if corners is not None:
        try:
            working = warp_to_rectangle(working, corners)
        except Exception:
            pass
    else:
        dewarped = None
        try:
            dewarped = dewarp_by_rulings(working)
        except Exception:
            dewarped = None
        if dewarped is not None:
            working = dewarped
            rectified = working  # skip trapezoid: bands already flat
        else:
            rectified = None
            try:
                rectified = rectify_from_rulings(working)
            except Exception:
                rectified = None
        if rectified is not None:
            working = rectified
        elif dewarped is None:
            try:
                working = deskew(working)
            except Exception:
                pass
        try:
            working = cut_dark_edge_bands(working)
            working = trim_white_fill_bands(working)
            working = trim_smeared_top_band(working)
        except Exception:
            pass
        if trim:
            try:
                working = auto_trim_margins(working)
            except Exception:
                pass
    enhanced = enhance_reference_look(
        working, ksize=ksize, white_point=white_point, black_point=black_point
    )
    if reframe:
        try:
            # IMPORTANT: cleanup passes must run AFTER re-framing. On a
            # full-frame phone photo the page edge IS the image border, so
            # running border/corner whitening before reframe erases real
            # content (e.g. the bottom ~16% of this page) and reframe then
            # centers a truncated document. In the reframed output, edges
            # are pure-white margins where artifact removal is safe.
            enhanced = reframe_like_reference(enhanced)
            enhanced = remove_binding_rings(enhanced)[0]
            enhanced = whiten_corner_smears(enhanced)
            enhanced = whiten_border_artifacts(enhanced)
        except Exception:
            pass
    if output_scale and abs(output_scale - 1.0) > 1e-6:
        try:
            enlarged = cv.resize(enhanced, None, fx=output_scale,
                                 fy=output_scale, interpolation=cv.INTER_LANCZOS4)
            blur = cv.GaussianBlur(enlarged, (0, 0), sigmaX=1.0)
            enhanced = cv.addWeighted(enlarged, 1.6, blur, -0.6, 0)
        except Exception:
            pass
    return enhanced
