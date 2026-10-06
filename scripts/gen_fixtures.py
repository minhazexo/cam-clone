"""Generate tiny synthetic parity fixtures for the opencv.js port.

Creates 800x1100 fake note photos (uneven light + 2-degree tilt + pink
ruling + text bars), runs them through the REAL Python pipeline, and saves
input/expected pairs under ``tests/fixtures/``. The Node parity harness
(Step 2+) diffs worker output against ``exp_*`` (MAD gate) — no PDFs needed.

Run (from the repository root)::

    python scripts/gen_fixtures.py

Regenerate ONLY when the pipeline change is intentional: fixtures are the
regression baseline for ``bun run parity``. See ``docs/TESTING.md``.
"""
import json
import os
import os.path as osp
import sys

# Dev scripts add the repository root so `import rscan` works when run by path
# (Python puts the script's own directory on sys.path[0]).
ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cv2 as cv  # noqa: E402
import numpy as np  # noqa: E402

from rscan.scanner.geometry import estimate_skew_angle  # noqa: E402
from rscan.scanner.photometry import enhance_reference_look  # noqa: E402
from rscan.scanner.pipeline import scan_photo_to_reference  # noqa: E402

OUT = osp.join(ROOT, "tests", "fixtures")
os.makedirs(OUT, exist_ok=True)

W, H = 800, 1100


def make_page(seed, tilt_deg, pink=True):
    rng = np.random.default_rng(seed)
    # Uneven-lit paper: vertical gradient 205..245 + noise.
    grad = np.linspace(205, 245, H, dtype=np.float32)[:, None]
    page = np.repeat(grad, W, axis=1)
    page += rng.normal(0, 3, (H, W)).astype(np.float32)
    img = np.stack([page, page, page], axis=-1)
    # Text bars.
    y = 150
    i = 0
    while y < H - 120:
        w_bar = int(450 + 100 * np.sin(i * 1.7))
        img[y:y + 14, 120:120 + w_bar] = (25, 25, 25)
        y += 52
        i += 1
    if pink:
        img[96:100, 40:W - 40] = (235, 130, 235)   # pink top ruling (BGR)
        img[60:H - 60, 72:76] = (235, 130, 235)    # pink left ruling
    # Dark left edge band (page-curl shadow).
    img[:, :18] = img[:, :18] * 0.55
    # Global tilt.
    m = cv.getRotationMatrix2D((W / 2.0, H / 2.0), tilt_deg, 1.0)
    img = cv.warpAffine(img, m, (W, H), flags=cv.INTER_CUBIC,
                        borderMode=cv.BORDER_CONSTANT, borderValue=(240, 240, 240))
    return np.clip(img, 0, 255).astype(np.uint8)


def sharpness(bgr):
    g = cv.cvtColor(bgr, cv.COLOR_BGR2GRAY)
    return float(cv.Laplacian(g, cv.CV_64F).var())


for name, tilt, pink in (("tilt_ruled", 2.0, True), ("tilt_plain", 2.0, False)):
    src = make_page(7 if pink else 8, tilt, pink)
    cv.imwrite(osp.join(OUT, f"in_{name}.png"), src)
    out = scan_photo_to_reference(src, output_scale=1.0)
    cv.imwrite(osp.join(OUT, f"exp_{name}.png"), out)
    ok, buf = cv.imencode(".jpg", out, [int(cv.IMWRITE_JPEG_QUALITY), 80])
    print(f"{name}: in_tilt~{tilt}deg out_tilt={estimate_skew_angle(out):.2f} "
          f"sharp_in={sharpness(src):.1f} sharp_out={sharpness(out):.1f} "
          f"out={out.shape[1]}x{out.shape[0]} q80={len(buf.tobytes())}B")
    # Step 2 (photometry-only) parity bytes for Node, which cannot decode PNG.
    # Mirrors the scale-1.0 branch of scan_photo_to_reference: enhance +
    # light unsharp (Gaussian sigma 0.8, addWeighted 1.3/-0.3), no geometry,
    # so dims stay W x H. The worker's processImage must reproduce these
    # bytes (MAD <= 3.0); the full-pipeline exp_*.png above is for Step 3+.
    photo = enhance_reference_look(src)
    _pblur = cv.GaussianBlur(photo, (0, 0), sigmaX=0.8)
    photo = cv.addWeighted(photo, 1.3, _pblur, -0.3, 0)
    assert photo.shape == src.shape, (photo.shape, src.shape)
    with open(osp.join(OUT, f"in_{name}.rgb"), "wb") as f:
        f.write(cv.cvtColor(src, cv.COLOR_BGR2RGB).tobytes())
    with open(osp.join(OUT, f"exp_{name}.rgb"), "wb") as f:
        f.write(cv.cvtColor(photo, cv.COLOR_BGR2RGB).tobytes())
    # Step 3 (geometry+full pipeline) parity bytes for Node, which cannot
    # decode PNG: the full-pipeline output (800x1100 in -> 790x1117/791x1119
    # out) as raw RGB, so tests/parity/parity_full.js can MAD-gate the JS
    # full pipeline against Python's pixels (gate MAD <= 3.0).
    with open(osp.join(OUT, f"full_{name}.rgb"), "wb") as f:
        f.write(cv.cvtColor(out, cv.COLOR_BGR2RGB).tobytes())
    with open(osp.join(OUT, f"{name}.json"), "w") as f:
        json.dump({
            "w": W, "h": H,
            "sharp_in": sharpness(src),
            "sharp_photo": sharpness(photo),
            "sharp_full": sharpness(out),
            "tilt_full": estimate_skew_angle(out),
            "full_w": int(out.shape[1]), "full_h": int(out.shape[0]),
        }, f)
    print(f"{name}: photo_only sharp_in={sharpness(src):.1f} "
          f"sharp_photo={sharpness(photo):.1f} dims={W}x{H}")
print("fixtures in", OUT)
