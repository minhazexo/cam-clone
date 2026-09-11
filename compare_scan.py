"""Diagnose remaining deltas between scanned output and reference.png.

Metrics:
  - dimensions of both images
  - full-image MAE / RMSE / PSNR (after resizing scan -> reference size)
  - ink-bounding-box margins as fractions of W/H (how content sits on canvas)
  - background (white) percentile stats + ink darkness stats
Writes a montage 'graphify-out/diag_v2.png' with the two images side by side
and a matched-size |diff| visualization.
"""
import os
import cv2 as cv
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(ROOT, "Work Images", "reference.png")
SCAN = os.path.join(ROOT, "Work Images", "scanned", "ecd285f44e7c.jpg")

ref = cv.imread(REF)
scan = cv.imread(SCAN)
print("ref :", None if ref is None else ref.shape)
print("scan:", None if scan is None else scan.shape)
if ref is None or scan is None:
    raise SystemExit(1)

# ---- size-matched comparison -------------------------------------------------
rh, rw = ref.shape[:2]
scaled = cv.resize(scan, (rw, rh), interpolation=cv.INTER_AREA)
resized = cv.resize(scan, (rw, rh), interpolation=cv.INTER_LANCZOS4)  # upscale quality
d = (resized.astype(np.float32) - ref.astype(np.float32))
m = np.abs(d)
mae = float(m.mean())
rmse = float(np.sqrt((d ** 2).mean()))
peak = 255.0
psnr = 20 * np.log10(peak / (rmse + 1e-9))
print(f"MAE={mae:.2f}  RMSE={rmse:.2f}  PSNR={psnr:.1f} dB")

# ---- per-channel MAE ---------------------------------------------------------
for i, ch in enumerate(["B", "G", "R"]):
    print(f"  MAE[{ch}] = {np.abs(d[:, :, i]).mean():.2f}")

# ---- reference vs scan brightness (bg + ink) ---------------------------------
def ink_stats(img):
    g = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
    return {
        "bg_median": int(np.median(g[g > 200])) if (g > 200).any() else None,
        "ink_pctl05": int(np.percentile(g, 5)),
        "ink_pctl10": int(np.percentile(g, 10)),
        "pct_white": float((g > 245).mean()),
        "pct_ink(<=128)": float((g <= 128).mean()),
        "pct_ink(<=60)": float((g <= 60).mean()),
    }

print("ref bg/ink :", ink_stats(ref))
print("scan bg/ink:", ink_stats(scaled))

def ink_bbox_margins(img, thr=160, min_area=15):
    g = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
    ink = g < thr
    n, lab, stats, _ = cv.connectedComponentsWithStats(ink.astype("uint8"), 8)
    keep = np.zeros_like(ink)
    for i in range(1, n):
        if stats[i, cv.CC_STAT_AREA] >= min_area:
            keep[lab == i] = True
    r = np.where(keep.any(axis=1))[0]
    c = np.where(keep.any(axis=0))[0]
    if r.size == 0:
        return None
    h, w = img.shape[:2]
    return {
        "left": round(c[0] / w, 4), "right": round(1 - c[-1] / w, 4),
        "top": round(r[0] / h, 4), "bottom": round(1 - r[-1] / h, 4),
    }

print("ref margins :", ink_bbox_margins(ref))
print("scan margins:", ink_bbox_margins(scaled))
print("ref margin constants in code: L=0.069 R=0.071 T=0.014 B=0.025")

# ---- diff visualization montage ----------------------------------------------
panel_h, panel_w = max(rh, resized.shape[0]), max(rw, resized.shape[1])
def panel(npimg):
    return cv.resize(npimg, (panel_w, panel_h), interpolation=cv.INTER_AREA)

g_ref = cv.cvtColor(panel(ref), cv.COLOR_BGR2GRAY)
g_scan = cv.cvtColor(panel(resized), cv.COLOR_BGR2GRAY)
diff = cv.absdiff(g_ref, g_scan)
diff_col = cv.applyColorMap(cv.convertScaleAbs(diff, alpha=3.0), cv.COLORMAP_JET)
vis = np.hstack([np.dstack([g_ref] * 3),
                 np.dstack([g_scan] * 3),
                 cv.cvtColor(diff_col, cv.COLOR_BGR2RGB)])
scale = 1600 / vis.shape[1]
out = cv.resize(vis, None, fx=scale, fy=scale, interpolation=cv.INTER_AREA)
os.makedirs(os.path.join(ROOT, "graphify-out"), exist_ok=True)
dst = os.path.join(ROOT, "graphify-out", "diag_v2.png")
cv.imwrite(dst, out)
print("wrote", dst)