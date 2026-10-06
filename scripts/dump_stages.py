"""Dump per-stage intermediates of the geometry pipeline for JS parity.

Reads ``tests/fixtures/in_<name>.png``, runs the REAL Python geometry stages on
RGB (browser convention; channel-symmetric + pink R-G identical), and saves
each stage as ``<stage>_<name>.rgb`` + ``stages_<name>.json`` {w,h,est,sharp}.

The chain replicates ``rscan.scanner.pipeline.scan_photo_to_reference``'s
geometry + post-enhance reframe/cleanup order exactly (trim=True,
ref_aspect=fallback) so ``tests/parity/parity_geometry.js`` can compare the
JavaScript port stage by stage.

Run (from the repository root)::

    python scripts/dump_stages.py
"""
import json
import os
import os.path as osp
import sys

# Dev scripts add the repository root so `import rscan` works when run by path.
ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cv2 as cv  # noqa: E402

from rscan.scanner import geometry as geom  # noqa: E402
from rscan.scanner import postprocessing as post  # noqa: E402
from rscan.scanner.constants import REF_ASPECT_FALLBACK  # noqa: E402
from rscan.scanner.photometry import enhance_reference_look  # noqa: E402

OUT = osp.join(ROOT, "tests", "fixtures")
REF_ASPECT = REF_ASPECT_FALLBACK


def sharp(bgr_or_rgb):
    g = cv.cvtColor(bgr_or_rgb, cv.COLOR_BGR2GRAY)
    return float(cv.Laplacian(g, cv.CV_64F).var())


def save_rgb(name, img_rgb):
    assert img_rgb.ndim == 3
    with open(osp.join(OUT, name + ".rgb"), "wb") as f:
        f.write(img_rgb.tobytes())
    return {"w": img_rgb.shape[1], "h": img_rgb.shape[0],
            "est": round(geom.estimate_skew_angle(
                cv.cvtColor(img_rgb, cv.COLOR_RGB2BGR)), 3),
            "sharp": round(sharp(img_rgb), 1)}


for name in ("tilt_ruled", "tilt_plain"):
    bgr = cv.imread(osp.join(OUT, f"in_{name}.png"), cv.IMREAD_COLOR)
    rgb = cv.cvtColor(bgr, cv.COLOR_BGR2RGB)
    m = {"input": save_rgb(f"st_input_{name}", rgb)}

    bgr_work = bgr
    try:
        corners = geom.find_document_contour(bgr_work)
    except Exception:
        corners = None
    m["contour"] = {"corners": None if corners is None else
                    [[round(float(x), 2), round(float(y), 2)] for x, y in corners]}
    if corners is not None:
        bgr_work = geom.warp_to_rectangle(bgr_work, corners)
        m["warp"] = save_rgb(f"st_warp_{name}",
                             cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))
        dewarped = rectified = None
    else:
        dewarped = geom.dewarp_by_rulings(bgr_work)
        m["dewarp"] = {"null": dewarped is None}
        if dewarped is not None:
            bgr_work = dewarped
            m["dewarp_img"] = save_rgb(f"st_dewarp_{name}",
                                       cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))
            rectified = bgr_work
        else:
            rectified = geom.rectify_from_rulings(bgr_work)
            m["rectify"] = {"null": rectified is None}
            if rectified is not None:
                bgr_work = rectified
                m["rectify_img"] = save_rgb(
                    f"st_rectify_{name}", cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))
            else:
                bgr_work = geom.deskew(bgr_work)
        m["geom_pretrim"] = save_rgb(f"st_pretrim_{name}",
                                     cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))
        bgr_work = post.cut_dark_edge_bands(bgr_work)
        bgr_work = post.trim_white_fill_bands(bgr_work)
        bgr_work = post.trim_smeared_top_band(bgr_work)
        bgr_work = post.auto_trim_margins(bgr_work)
        m["geom_chain"] = save_rgb(f"st_geom_{name}",
                                   cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))

    enh = enhance_reference_look(bgr_work)
    m["enhanced"] = save_rgb(f"st_enh_{name}",
                             cv.cvtColor(enh, cv.COLOR_BGR2RGB))
    ref = post.reframe_like_reference(enh, ref_aspect=REF_ASPECT)
    m["reframe"] = save_rgb(f"st_reframe_{name}",
                            cv.cvtColor(ref, cv.COLOR_BGR2RGB))
    rb, removed = post.remove_binding_rings(ref)
    m["binding"] = {"removed": bool(removed)}
    m["binding_img"] = save_rgb(f"st_binding_{name}",
                                cv.cvtColor(rb, cv.COLOR_BGR2RGB))
    wc = post.whiten_corner_smears(rb)
    m["corner"] = save_rgb(f"st_corner_{name}",
                           cv.cvtColor(wc, cv.COLOR_BGR2RGB))
    wb = post.whiten_border_artifacts(wc)
    m["border"] = save_rgb(f"st_border_{name}",
                           cv.cvtColor(wb, cv.COLOR_BGR2RGB))

    with open(osp.join(OUT, f"stages_{name}.json"), "w") as f:
        json.dump(m, f, indent=1)
    print(name, "geom:", m.get("geom_chain"), "border:", m["border"])
