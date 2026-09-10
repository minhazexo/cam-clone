"""Quality gate: compare pipeline output on 1.jpg against reference.jpg.

The gate is anchored to ``reference.png`` itself: the same statistics are
measured on both the reference and the pipeline output (both downscaled to
the same working width), and each check asserts the output stays inside a
tight band around the reference value. Extra hard limits keep edges / tilt
clean. This catches washed-out ink, lost color, contrast drift and layout
regressions instead of only passing when the image is "white enough".

Usage: python quality_gate.py [--out DIR]
"""
import argparse
import os
import sys

import cv2 as cv
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from auto_scan import estimate_skew_angle, scan_photo_to_reference

BASE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(BASE, "wiki_images", "pdf photo..jpg")
REF = os.path.join(BASE, "wiki_images", "reference.png")

WORKING_W = 480


def downscale_to_width(img, width=WORKING_W):
    h, w = img.shape[:2]
    if w <= width:
        return img.copy()
    return cv.resize(img, (width, int(h * width / w)),
                     interpolation=cv.INTER_AREA)


def stats(bgr):
    """Reference-anchored statistics measured on the given image."""
    g = cv.cvtColor(bgr, cv.COLOR_BGR2GRAY).astype(np.float32)
    b, g2, r = cv.split(bgr.astype(np.float32))
    chroma = np.abs(r - b) + np.abs(g2 - b) + np.abs(r - g2)
    dark = g[g < 200]
    return {
        "gray_mean": float(g.mean()),
        "gray_std": float(g.std()),
        "ink_mean": float(dark.mean()) if len(dark) else 0.0,
        "vd_90": float(100 * (g < 90).mean()),
        "dark_128": float(100 * (g < 128).mean()),
        "chroma99": float(np.percentile(chroma, 99)),
    }


def ssim_gray(a, b):
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    mu_a = cv.GaussianBlur(a, (11, 11), 1.5)
    mu_b = cv.GaussianBlur(b, (11, 11), 1.5)
    s_a2 = cv.GaussianBlur(a * a, (11, 11), 1.5) - mu_a * mu_a
    s_b2 = cv.GaussianBlur(b * b, (11, 11), 1.5) - mu_b * mu_b
    s_ab = cv.GaussianBlur(a * b, (11, 11), 1.5) - mu_a * mu_b
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    m = ((2 * mu_a * mu_b + c1) * (2 * s_ab + c2)
         / ((mu_a ** 2 + mu_b ** 2 + c1) * (s_a2 + s_b2 + c2)))
    return float(m.mean())


def shared_roi_stats(a, b, align=True):
    """PSNR / SSIM / MAD on the region where both images contain ink.

    Both inputs must already share the same size. ``align`` runs a
    translation/rotation/scale ECC fit so content overlays as best as the
    differing resolutions allow (it measures processing quality, not layout
    alignment). Only the shared content area (plus a small pad) is scored so
    the huge white canvases do not bias the numbers.
    """
    if align:
        warp = np.eye(2, 3, dtype=np.float32)
        criteria = (cv.TERM_CRITERIA_EPS | cv.TERM_CRITERIA_COUNT, 200, 1e-5)
        try:
            _, warp = cv.findTransformECC(a, b, warp, cv.MOTION_AFFINE,
                                          criteria, None, 1)
            b = cv.warpAffine(b, warp, (a.shape[1], a.shape[0]),
                              flags=cv.INTER_LINEAR + cv.WARP_INVERSE_MAP)
        except Exception:
            pass
    ink_mask = ((a < 180) | (b < 180)).astype(np.float32)
    if ink_mask.sum() <= 100:
        return None
    ink_mask = cv.dilate(ink_mask, np.ones((5, 5), np.float32))
    rows = np.where(ink_mask.any(axis=1))[0]
    cols = np.where(ink_mask.any(axis=0))[0]
    y0, y1 = int(max(0, rows[0] - 5)), int(min(a.shape[0], rows[-1] + 6))
    x0, x1 = int(max(0, cols[0] - 5)), int(min(a.shape[1], cols[-1] + 6))
    a_r, b_r = a[y0:y1, x0:x1], b[y0:y1, x0:x1]
    mse = float(((a_r - b_r) ** 2).mean())
    psnr = 10 * np.log10(255 * 255 / max(mse, 1e-9))
    ssim = ssim_gray(a_r, b_r)
    mad = float(np.abs(a_r - b_r).mean())
    return psnr, ssim, mad


def ink_bbox(gray, thresh=100):
    ink = gray < thresh
    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    h, w = gray.shape[:2]
    return (rows.min() / h, rows.max() / h, cols.min() / w, cols.max() / w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(BASE, "wiki_images", "scanned"))
    args = ap.parse_args()

    src = cv.imread(SRC, cv.IMREAD_COLOR)
    ref = cv.imread(REF, cv.IMREAD_COLOR)
    assert src is not None and ref is not None

    out = scan_photo_to_reference(src)
    os.makedirs(args.out, exist_ok=True)
    cv.imwrite(os.path.join(args.out, "page_0001.jpg"), out,
               [int(cv.IMWRITE_JPEG_QUALITY), 90])

    # Same working scale for both -> fair statistics comparison.
    out_small = downscale_to_width(out)
    ref_small = downscale_to_width(ref)

    ref_st = stats(ref_small)
    out_st = stats(out_small)
    out_h, out_w = out_small.shape[:2]
    ref_h, ref_w = ref_small.shape[:2]
    if (out_h, out_w) != (ref_h, ref_w):
        out_small = cv.resize(out_small, (ref_w, ref_h), interpolation=cv.INTER_AREA)

    g_out = cv.cvtColor(out_small, cv.COLOR_BGR2GRAY).astype(np.float32)
    g_ref = cv.cvtColor(ref_small, cv.COLOR_BGR2GRAY).astype(np.float32)
    roi = shared_roi_stats(g_out, g_ref)

    results = []

    def check(name, value, lo, hi, fmt="%.2f"):
        ok = lo <= value <= hi
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}={fmt % value} "
              f"(want {lo:.3f}..{hi:.3f})")

    def anchor(name, value, ref_value, tol):
        check(name, value, ref_value - tol, ref_value + tol)

    # Photometry vs reference (tolerance slightly wider than pixel noise).
    anchor("gray_mean", out_st["gray_mean"], ref_st["gray_mean"], 5.0)
    anchor("gray_std", out_st["gray_std"], ref_st["gray_std"], 12.0)
    anchor("ink_mean", out_st["ink_mean"], ref_st["ink_mean"], 15.0)
    anchor("vd_90", out_st["vd_90"], ref_st["vd_90"], 2.0)
    anchor("dark_128", out_st["dark_128"], ref_st["dark_128"], 2.5)
    anchor("chroma99", out_st["chroma99"], ref_st["chroma99"], 20.0)

    if roi is not None:
        psnr, ssim, mad = roi
        check("PSNR(dB)", psnr, 8.0, 100.0)
        check("SSIM", ssim, 0.32, 1.0)
        check("MAD", mad, 0.0, 55.0)

    check("resid_tilt", estimate_skew_angle(out), -0.35, 0.35)
    check("ref_tilt", estimate_skew_angle(ref), -0.35, 0.35)

    h, w = out.shape[:2]
    g = cv.cvtColor(out, cv.COLOR_BGR2GRAY)
    b = max(1, int(h * 0.02))
    bw_ = max(1, int(w * 0.02))
    for sname, strip in [("edge_top", g[:b, :]), ("edge_bot", g[-b:, :]),
                         ("edge_l", g[:, :bw_]), ("edge_r", g[:, -bw_:])]:
        check(f"{sname}_darkpct", 100 * float((strip < 100).mean()), 0.0, 0.5,
              fmt="%.3f")

    r0, r1, c0, c1 = ink_bbox(g)
    rr0, rr1, cc0, cc1 = ink_bbox(cv.cvtColor(ref, cv.COLOR_BGR2GRAY))
    check("marg_top", r0, rr0 - 0.025, rr0 + 0.025, fmt="%.3f")
    check("marg_bot", r1, rr1 - 0.05, rr1 + 0.025, fmt="%.3f")
    check("marg_l", c0, cc0 - 0.02, cc0 + 0.02, fmt="%.3f")
    check("marg_r", c1, cc1 - 0.02, cc1 + 0.02, fmt="%.3f")

    print(f"output shape: {out.shape[1]}x{out.shape[0]} "
          f"ref: {ref.shape[1]}x{ref.shape[0]}")
    print("ALL PASS" if all(results) else "SOME CHECKS FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())