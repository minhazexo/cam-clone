"""Dump tests/fixtures/in_*.png to raw RGB + JSON sidecars for the Node harness.

Node cannot decode PNG, so the parity harness reads .rgb bytes (row-major RGB)
plus a tiny .json with {w, h}. Run: python scripts/dump_rgb.py
"""
import json
import os

import cv2 as cv

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "tests", "fixtures")

for name in ("in_tilt_ruled", "in_tilt_plain"):
    src = cv.imread(os.path.join(FIX, name + ".png"), cv.IMREAD_COLOR)
    assert src is not None, name
    rgb = cv.cvtColor(src, cv.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    with open(os.path.join(FIX, name + ".rgb"), "wb") as f:
        f.write(rgb.tobytes())
    with open(os.path.join(FIX, name + ".json"), "w") as f:
        json.dump({"w": w, "h": h}, f)
    print(name, "->", name + ".rgb", w, "x", h)
