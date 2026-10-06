"""Generate tests/fixtures/receipt_dims.json — the canvas-budget parity anchor.

Runs the canonical long receipt (mirrored byte-for-byte by
tests/parity/parity_receipt.js and tests/unit/test_scanner.py:make_receipt)
through reframe_like_reference and the full pipeline, and records the
resulting dimensions. The Node harness compares the JS pipeline against this
anchor, so a drift on either side fails the parity gate — without committing
multi-MB pixel dumps for a 400x8000 page.

Usage (from the repository root):

    python scripts/gen_receipt_fixture.py

Regenerate ONLY when the pipeline change is intentional (the JSON is the
regression baseline for `bun run parity`). See docs/TESTING.md.
"""
from __future__ import annotations

import json
import os.path as osp
import sys
import time

# Dev scripts add the repository root so `import rscan` works when run by path.
ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rscan.scanner.constants import REF_ASPECT_FALLBACK  # noqa: E402
from rscan.scanner.pipeline import scan_photo_to_reference  # noqa: E402
from rscan.scanner.postprocessing import reframe_like_reference  # noqa: E402
from tests.unit.test_scanner import make_receipt  # noqa: E402

OUT = osp.join(ROOT, "tests", "fixtures", "receipt_dims.json")


def main() -> None:
    receipt = make_receipt()
    h, w = receipt.shape[:2]

    t0 = time.time()
    re = reframe_like_reference(receipt, ref_aspect=REF_ASPECT_FALLBACK)
    t_re = time.time() - t0
    t0 = time.time()
    full = scan_photo_to_reference(receipt, output_scale=1.0)
    t_full = time.time() - t0

    anchor = {
        "w": w,
        "h": h,
        "reframe": [int(re.shape[1]), int(re.shape[0])],
        "full": [int(full.shape[1]), int(full.shape[0])],
        "ref_aspect": REF_ASPECT_FALLBACK,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(anchor, fh, indent=2)
        fh.write("\n")
    print(f"reframe {anchor['reframe']} ({t_re:.1f}s), "
          f"full {anchor['full']} ({t_full:.1f}s) -> {OUT}")


if __name__ == "__main__":
    main()
