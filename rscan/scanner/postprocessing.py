"""Postprocessing stage: trims, reframing, artifact cleanup.

Pipeline position: partly BEFORE photometry (edge/shadow trims operate on the
raw rectified photo, where shadows are still dark and separable), mostly
AFTER photometry (binding removal, border whitening and re-framing operate on
the enhanced image where paper is pure white and artifacts are obvious).

Ordering inside ``pipeline.scan_photo_to_reference`` is load-bearing — see the
comments on each call site there. Two traps worth repeating:

    * cleanup passes must run AFTER re-framing, otherwise border whitening
      erases real content on full-frame photos;
    * binding rings are inpainted on the unrotated reframed canvas, because
      residual rotation antialiases ring cores below the thickness gate.

Parity note: mirrored in ``static/js/workers/scan-geometry.js``
(trimWhiteFillBands, trimSmearedTopBand, cutDarkEdgeBands, autoTrimMargins,
reframeLikeReference, removeBindingRings, whitenCornerSmears,
whitenBorderArtifacts).
"""

from __future__ import annotations

import math

import cv2 as cv
import numpy as np

from rscan.scanner.constants import (
    REF_CANVAS_MAX_PIXELS,
    REF_MARGIN_BOTTOM,
    REF_MARGIN_LEFT,
    REF_MARGIN_RIGHT,
    REF_MARGIN_TOP,
)
from rscan.scanner.reference import measure_reference_size


def trim_white_fill_bands(image: np.ndarray, ink_threshold: int = 240,
                          max_fraction: float = 0.08) -> np.ndarray:
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


def trim_smeared_top_band(image: np.ndarray, max_fraction: float = 0.10,
                          thresh_ratio: float = 0.50) -> np.ndarray:
    """Cut a warp-smeared band at the top edge, if present.

    Perspective extrapolation can stretch near-edge content into a blurry
    strip; desk bands behind the page are equally texture-free. Detect rows
    with almost no edge energy and drop them (capped at ``max_fraction`` of
    height). The 0.50 ratio (not lower) is load-bearing: real content rows
    always carry stroke energy well above half the page median, while
    uniform desk/shadow rows sit far below it. No-op on already-clean pages.
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


def edge_darkness_profile(gray: np.ndarray, thresh: int = 100, smooth: int = 15,
                          win_frac: float = 0.25) -> np.ndarray:
    """Per-column dark fraction, maxed over sliding row windows.

    Averaging over the whole page height dilutes shadow/coil bands that
    only span *part* of the page: on a full-frame photo the page-gap
    shadow (left) and the spiral coil (right) both live near the top, so a
    whole-page mean falls below any sane threshold and no cut fires. Taking
    the elementwise max over overlapping windows keeps a part-height band
    visible while columns through sparse text stay low (text does not fill
    a whole window the way a solid shadow band does).
    """
    h, w = gray.shape
    win = max(1, int(h * win_frac))
    step = max(1, win // 2)
    profile = np.zeros(w, dtype=np.float64)
    for y0 in range(0, max(1, h - win + 1), step):
        band = gray[y0:y0 + win, :] < thresh
        profile = np.maximum(profile, band.mean(axis=0))
    kernel = np.ones(smooth) / float(smooth)
    return np.convolve(profile, kernel, mode="same")


def cut_dark_edge_bands(image: np.ndarray, left_thresh: float = 0.25,
                        right_thresh: float = 0.13,
                        left_cap: float = 0.06, right_cap: float = 0.16,
                        smooth: int = 15,
                        min_coil_width_ratio: float = 0.04) -> np.ndarray:
    """Cut the page-gap shadow (left) adaptively; never touch the right.

    Operates on the rectified but NOT yet enhanced photo. Already-clean
    scans (bright overall) are returned untouched. Left: the gap shadow is
    *solid* dark, so a high sustained threshold never touches text. Right:
    deliberately no cut — dense content sustains edge darkness exactly like
    coil bands, and every automatic right cut tested ate real text; coil
    cosmetics belong to remove_binding_rings, and reference outputs keep
    the binding visible. No-op if nothing qualifies.
    """
    h, w = image.shape[:2]
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY) if image.ndim == 3 else image
    if float(gray.mean()) > 200:
        return image  # already a clean scan; nothing to cut
    smooth_frac = edge_darkness_profile(gray, smooth=smooth)
    x0 = 0
    while x0 <= int(w * left_cap) and smooth_frac[x0] > left_thresh:
        x0 += 1
    # Right side: NO cut. Dense page content (tables, handwriting) sustains
    # high edge darkness exactly like coil bands do, so any profile- or
    # mass-based right cut eats real text (verified: a 193px cut removed
    # table equations while the mass gate still stopped inside content).
    # Coil cosmetics belong to remove_binding_rings (precise inpaint), and
    # reference outputs keep the binding visible anyway. Never cut right.
    x1 = w
    if x1 - x0 < w // 2:
        return image
    return image[:, x0:x1]


def reframe_like_reference(image: np.ndarray, ink_threshold: int = 160,
                           left: float = REF_MARGIN_LEFT,
                           right: float = REF_MARGIN_RIGHT,
                           top: float = REF_MARGIN_TOP,
                           bottom: float = REF_MARGIN_BOTTOM,
                           ref_aspect: float | None = None) -> np.ndarray:
    """Re-frame a scanned page to the reference's edge/placement quality.

    Takes the ink bounding box (faint watermarks above ``ink_threshold``
    stay out of the box) and centers it on a white canvas with the same
    symmetric margins as reference.png. Edges become pure white; nothing
    is distorted (aspect follows the content).

    When ``ref_aspect`` is given (reference width / reference height),
    the canvas aspect ratio is constrained to match the reference,
    ensuring consistent output sizing regardless of input proportions.
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
    # Fringe extension: faint content (watermarks, pencil, anti-aliased
    # edges) just outside the dark-ink box must not be dropped from the
    # canvas. Reach outward up to 1.5% per side, but only through faint ink
    # (< 200) — bounded, so shadows can't blow up the page.
    faint = gray < 200
    pad_y, pad_x = max(1, int(h * 0.015)), max(1, int(w * 0.015))
    up = np.where(faint[max(0, y0 - pad_y):y0, x0:x1].any(axis=1))[0]
    if len(up):
        y0 = max(0, y0 - pad_y) + int(up.min())
    dn = np.where(faint[y1:min(h, y1 + pad_y), x0:x1].any(axis=1))[0]
    if len(dn):
        y1 = min(y1 + int(dn.max()) + 1, h)
    lf = np.where(faint[y0:y1, max(0, x0 - pad_x):x0].any(axis=0))[0]
    if len(lf):
        x0 = max(0, x0 - pad_x) + int(lf.min())
    rt = np.where(faint[y0:y1, x1:min(w, x1 + pad_x)].any(axis=0))[0]
    if len(rt):
        x1 = min(x1 + int(rt.max()) + 1, w)
    bw, bh = x1 - x0, y1 - y0

    if bw < w // 4 or bh < h // 4:
        return image  # degenerate detection; keep input

    ref_size = measure_reference_size()
    if ref_size is not None and ref_aspect is not None:
        canvas_h, canvas_w = ref_size
        target_w = int(round(canvas_w * (1.0 - left - right)))
        target_h = int(round(canvas_h * (1.0 - top - bottom)))
        content = cv.resize(image[y0:y1, x0:x1], (target_w, target_h),
                            interpolation=cv.INTER_LANCZOS4)
        if image.ndim == 3:
            canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
        else:
            canvas = np.full((canvas_h, canvas_w), 255, dtype=np.uint8)
        ox = int(round(left * canvas_w))
        oy = int(round(top * canvas_h))
        canvas[oy:oy + target_h, ox:ox + target_w] = content
        return canvas

    if ref_aspect is not None:
        # Compute the minimum canvas dimensions that satisfy the specified
        # margins in BOTH width and height directions simultaneously.
        #
        #   canvas_w >= bw / (1 - left - right)   (horizontal margin constraint)
        #   canvas_h >= bh / (1 - top - bottom)   (vertical margin constraint)
        #   canvas_w / canvas_h ~= ref_aspect        (aspect target)
        #
        # When content aspect != ref_aspect, these three constraints may be
        # incompatible. Resolve by using the height-constrained canvas
        # (canvas_h = min_canvas_h) with width = max(min_canvas_w,
        # aspect_w_for_h). This guarantees both margins are met; the aspect
        # ratio may deviate slightly from ref_aspect when the content is
        # intrinsically a different shape than the reference page.
        min_canvas_w = int(round(bw / max(1e-6, 1.0 - left - right)))
        min_canvas_h = int(round(bh / max(1e-6, 1.0 - top - bottom)))

        # Height-constrained canvas: use min_canvas_h as the canvas height,
        # width from aspect ratio (but not less than min_canvas_w).
        aspect_w_for_h = int(round(min_canvas_h * ref_aspect))
        canvas_h = min_canvas_h
        canvas_w = max(min_canvas_w, aspect_w_for_h)
    else:
        canvas_w = int(round(bw / max(1e-6, 1.0 - left - right)))
        canvas_h = int(round(bh / max(1e-6, 1.0 - top - bottom)))
    # Pixel budget: scale canvas and content down uniformly when the canvas
    # exceeds REF_CANVAS_MAX_PIXELS (extreme-aspect inputs widen to the
    # reference aspect and would otherwise explode — 54 MP for a long
    # receipt — which the browser worker's WASM heap cannot hold). The
    # uniform scale keeps margins/aspect intact, so the final A4-embedded
    # output is unchanged; only redundant white pixels are dropped.
    # Parity-sensitive: scan-geometry.js applies the identical formula.
    content = image[y0:y1, x0:x1]
    if canvas_w * canvas_h > REF_CANVAS_MAX_PIXELS:
        scale = math.sqrt(REF_CANVAS_MAX_PIXELS / (canvas_w * canvas_h))
        content = cv.resize(
            content,
            (max(1, int(round(bw * scale))), max(1, int(round(bh * scale)))),
            interpolation=cv.INTER_LANCZOS4)
        canvas_w = max(1, int(round(canvas_w * scale)))
        canvas_h = max(1, int(round(canvas_h * scale)))
        bh = content.shape[0]
        bw = content.shape[1]
    ox = int(round((canvas_w - bw) / 2.0))
    oy_top = int(round(top * canvas_h))
    # Independent rounding of the scaled dims can shift the paste by ±1 px:
    # clamp identically in both implementations (a no-op when it fits).
    ox = max(0, min(ox, canvas_w - bw))
    oy_top = max(0, min(oy_top, canvas_h - bh))
    PAPER_GRAY = 255  # let HPF provide natural paper tone in content area
    if image.ndim == 3:
        canvas = np.full((canvas_h, canvas_w, 3), PAPER_GRAY, dtype=np.uint8)
        canvas[oy_top:oy_top + bh, ox:ox + bw] = content
    else:
        canvas = np.full((canvas_h, canvas_w), PAPER_GRAY, dtype=np.uint8)
        canvas[oy_top:oy_top + bh, ox:ox + bw] = content
    return canvas


def trim_coil_margin(image: np.ndarray, zone_width: float = 0.12,
                     row_lo: float = 0.10, row_hi: float = 0.92,
                     dark_thresh: int = 140) -> np.ndarray:
    """Cut sparse spiral-coil marks from left/right margins of enhanced image.

    Strategy: in the margin zone, cluster dark pixels into connected
    components.  Coil marks are small isolated blobs; text strokes form
    large connected groups.  Trims from each edge inward until encountering
    a component wider than ``min_text_width`` pixels.

    Status: implemented and parity-ported, but currently NOT called by the
    pipeline (kept because the JS port exposes it and future coil work needs
    it). Do not delete without checking ``scan-geometry.js``.
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


def auto_trim_margins(image: np.ndarray, left: float = 0.008, right: float = 0.02,
                      top: float = 0.01, bottom: float = 0.02,
                      ink_threshold: int = 160,
                      band_top: float = 0.12, band_bottom: float = 0.12,
                      band_left: float = 0.08, band_right: float = 0.08) -> np.ndarray:
    """Micro-border trim that never eats content, in two tiers.

    Tier 1 removes ink-free outer rows/cols (rotation-fill triangles, warp
    slivers) within small caps. Tier 2 removed dark BANDS (desk, vignette);
    that tier was deleted because on dark-background headers (white text on
    desk shadow has identical statistics to the shadow itself) it ate real
    content — see the comment below. Desk bands are removed instead by the
    post-enhance top trim in the pipeline, where enhancement has already
    turned background white and text black. The ``band_*`` parameters are
    kept for API compatibility only.
    """
    h, w = image.shape[:2]
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY) if image.ndim == 3 else image
    has_ink_col = (gray.min(axis=0) <= ink_threshold)
    has_ink_row = (gray.min(axis=1) <= ink_threshold)

    # Tier 1: ink-free, small caps.
    x0 = 0
    while x0 <= int(w * left) and not has_ink_col[x0]:
        x0 += 1
    x1 = w
    while x1 > w - int(w * right) and not has_ink_col[x1 - 1]:
        x1 -= 1
    y0 = 0
    while y0 <= int(h * top) and not has_ink_row[y0]:
        y0 += 1
    y1 = h
    while y1 > h - int(h * bottom) and not has_ink_row[y1 - 1]:
        y1 -= 1

    # Tier 2 removed (see docstring): band_* params kept for API
    # compatibility only. Desk bands are removed by the post-enhance top
    # trim in pipeline.scan_photo_to_reference instead.
    if x1 - x0 < w // 2 or y1 - y0 < h // 2:
        return image
    if x0 == 0 and y0 == 0 and x1 == w and y1 == h:
        return image
    return image[y0:y1, x0:x1]


def remove_binding_rings(image: np.ndarray, zone_ratio: float = 0.78,
                         dark: int = 70, min_thick: float = 2.0,
                         min_height: int = 20, min_area: int = 40):
    """Erase spiral-binding rings overlapping the page (inpaint with paper).

    Rings are the only structures that are simultaneously very dark, thick
    (distance-transform radius), tall, non-horizontal, and living in the
    right edge zone. Horizontal rulings are subtracted first; thin ink
    strokes never qualify by thickness/height. A second pass catches ring
    *edges*: metallic rings photograph with bright cores, so only their
    outlines are dark (too thin for the thickness gate) — but those
    outlines form long straight diagonals sharing one dominant angle,
    which handwriting never does. That pass is adaptive (peak angle,
    vertical notch for table borders, length gate, 3% area cap) and only
    fires with >= 5 agreeing segments. Operates on the *enhanced* image
    where rings are pure black on white paper. Returns (image,
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
    # Grow slightly into anti-aliased ring edges.
    mask = cv.dilate(mask, cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5)))
    # Union with the diagonal pass (metallic bright-core rings whose
    # outlines are too thin for the thickness gate but share one dominant
    # diagonal angle — see diagonal_ring_mask, returns a full-size mask
    # or None).
    diag = diagonal_ring_mask(gray, zone_ratio)
    if diag is not None:
        mask = np.maximum(mask, diag)
    if int((mask > 0).sum()) < 50:
        return work, False
    # cv.inpaint handles both BGR and single-channel inputs.
    work = cv.inpaint(work, mask, 5, cv.INPAINT_TELEA)
    return work, True


def diagonal_ring_mask(gray: np.ndarray, zone_ratio: float = 0.78):
    """Mask of dominant-diagonal long segments in the right zone, or None.

    Returns None unless >= 5 segments agree on a 5-degree peak (outside the
    86-94 vertical notch that protects table borders), each >= 80px long,
    and the dilated total stays under 3% of the image (catastrophe guard).
    Handwriting never produces this signature; spiral rings always do.
    """
    h, w = gray.shape[:2]
    zx = int(w * zone_ratio)
    zone = gray[:, zx:]
    edges = cv.Canny(zone, 50, 150)
    lines = cv.HoughLinesP(edges, 1, np.pi / 180, 80,
                           minLineLength=80, maxLineGap=12)
    if lines is None or len(lines) < 5:
        return None
    angs = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        a = math.degrees(math.atan2(y2 - y1, x2 - x1))
        a = abs(a) if abs(a) <= 90 else 180 - abs(a)  # 0..90 line angle
        if 55.0 <= a <= 90.0 and not 86.0 <= a <= 94.0:
            angs.append(((x1, y1, x2, y2), a, math.hypot(x2 - x1, y2 - y1)))
    if len(angs) < 5:
        return None
    hist = {}
    for _, a, _ in angs:
        hist[int(a // 5) * 5] = hist.get(int(a // 5) * 5, 0) + 1
    peak = max(hist, key=hist.get)
    if hist[peak] < 5:
        return None
    diag = np.zeros_like(zone)
    for (x1, y1, x2, y2), a, ln in angs:
        if ln >= 80 and abs(a - (peak + 2.5)) <= 10.0:
            cv.line(diag, (x1, y1), (x2, y2), 255, 1)
    diag = cv.dilate(diag, cv.getStructuringElement(cv.MORPH_ELLIPSE, (7, 7)))
    if int((diag > 0).sum()) > 0.03 * h * w:
        return None
    full = np.zeros((h, w), np.uint8)
    full[:, zx:] = diag
    return full


def whiten_corner_smears(image: np.ndarray, bright_lo: int = 150,
                         diff: int = 18, max_ratio: float = 0.06) -> np.ndarray:
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


def whiten_border_artifacts(image: np.ndarray, ink_threshold: int = 160,
                            max_depth_ratio: float = 0.12) -> np.ndarray:
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


__all__ = [
    "trim_white_fill_bands",
    "trim_smeared_top_band",
    "edge_darkness_profile",
    "cut_dark_edge_bands",
    "reframe_like_reference",
    "trim_coil_margin",
    "auto_trim_margins",
    "remove_binding_rings",
    "diagonal_ring_mask",
    "whiten_corner_smears",
    "whiten_border_artifacts",
]
