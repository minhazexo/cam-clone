"""Dump per-stage intermediates of the geometry pipeline for JS parity.

Reads tests/fixtures/in_<name>.png, runs the REAL Python geometry stages on
RGB (browser convention; channel-symmetric + pink R-G identical), saves each
stage as <stage>_<name>.rgb + stages_<name>.json {w,h,est,sharp}.
aku chain replicates scan_photo_to_reference lines 1043-1088 + post-enhance
reframe/cleanups exactly (trim=True, ref_aspect=fallback).
"""
import json
import os
import sys

import cv2 as cv
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "RScan", "Python", "scan"))
import auto_scan as A

OUT = os.path.join(HERE, "..", "tests", "fixtures")
REF_ASPECT = 893.0 / 1263.0


def sharp(bgr_or_rgb):
    g = cv.cvtColor(bgr_or_rgb, cv.COLOR_BGR2GRAY)
    return float(cv.Laplacian(g, cv.CV_64F).var())


def save_rgb(name, img_rgb):
    assert img_rgb.ndim == 3
    with open(os.path.join(OUT, name + ".rgb"), "wb") as f:
        f.write(img_rgb.tobytes())
    return {"w": img_rgb.shape[1], "h": img_rgb.shape[0],
            "est": round(A.estimate_skew_angle(
                cv.cvtColor(img_rgb, cv.COLOR_RGB2BGR)), 3),
            "sharp": round(sharp(img_rgb), 1)}


for name in ("tilt_ruled", "tilt_plain"):
    bgr = cv.imread(os.path.join(OUT, f"in_{name}.png"), cv.IMREAD_COLOR)
    rgb = cv.cvtColor(bgr, cv.COLOR_BGR2RGB)
    m = {"input": save_rgb(f"st_input_{name}", rgb)}

    bgr_work = bgr
    try:
        corners = A.find_document_contour(bgr_work)
    except Exception:
        corners = None
    m["contour"] = {"corners": None if corners is None else
                    [[round(float(x), 2), round(float(y), 2)] for x, y in corners]}
    if corners is not None:
        bgr_work = A.warp_to_rectangle(bgr_work, corners)
        m["warp"] = save_rgb(f"st_warp_{name}",
                             cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))
        dewarped = rectified = None
    else:
        dewarped = A.dewarp_by_rulings(bgr_work)
        m["dewarp"] = {"null": dewarped is None}
        if dewarped is not None:
            bgr_work = dewarped
            m["dewarp_img"] = save_rgb(f"st_dewarp_{name}",
                                       cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))
            rectified = bgr_work
        else:
            rectified = A.rectify_from_rulings(bgr_work)
            m["rectify"] = {"null": rectified is None}
            if rectified is not None:
                bgr_work = rectified
                m["rectify_img"] = save_rgb(
                    f"st_rectify_{name}", cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))
            else:
                bgr_work = A.deskew(bgr_work)
        m["geom_pretrim"] = save_rgb(f"st_pretrim_{name}",
                                     cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))
        bgr_work = A.cut_dark_edge_bands(bgr_work)
        bgr_work = A.trim_white_fill_bands(bgr_work)
        bgr_work = A.trim_smeared_top_band(bgr_work)
        bgr_work = A.auto_trim_margins(bgr_work)
        m["geom_chain"] = save_rgb(f"st_geom_{name}",
                                   cv.cvtColor(bgr_work, cv.COLOR_BGR2RGB))

    from auto_scan import enhance_reference_look
    enh = enhance_reference_look(bgr_work)
    m["enhanced"] = save_rgb(f"st_enh_{name}",
                             cv.cvtColor(enh, cv.COLOR_BGR2RGB))
    ref = A.reframe_like_reference(enh, ref_aspect=REF_ASPECT)
    m["reframe"] = save_rgb(f"st_reframe_{name}",
                            cv.cvtColor(ref, cv.COLOR_BGR2RGB))
    rb, removed = A.remove_binding_rings(ref)
    m["binding"] = {"removed": bool(removed)}
    m["binding_img"] = save_rgb(f"st_binding_{name}",
                                cv.cvtColor(rb, cv.COLOR_BGR2RGB))
    wc = A.whiten_corner_smears(rb)
    m["corner"] = save_rgb(f"st_corner_{name}",
                           cv.cvtColor(wc, cv.COLOR_BGR2RGB))
    wb = A.whiten_border_artifacts(wc)
    m["border"] = save_rgb(f"st_border_{name}",
                           cv.cvtColor(wb, cv.COLOR_BGR2RGB))

    with open(os.path.join(OUT, f"stages_{name}.json"), "w") as f:
        json.dump(m, f, indent=1)
    print(name, "geom:", m.get("geom_chain"), "border:", m["border"])
