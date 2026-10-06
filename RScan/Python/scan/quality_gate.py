"""DEPRECATED MODULE — the quality gate moved to ``scripts/quality_gate.py``.

Status: **compatibility shim**.

The reference-anchored regression gate now lives with the other dev tooling::

    python scripts/quality_gate.py [--out DIR]

This shim keeps the historical command working::

    python RScan/Python/scan/quality_gate.py

It loads the moved module by file path (no ``sys.path`` juggling) and
re-exports its public helpers for any old caller that imported them.
"""

from __future__ import annotations

import importlib.util
import os

TARGET = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "scripts", "quality_gate.py",
)


def _load_moved_module():
    """Execute ``scripts/quality_gate.py`` and return the module object."""
    spec = importlib.util.spec_from_file_location("rscan_quality_gate", TARGET)
    if spec is None or spec.loader is None:  # pragma: no cover - repo layout
        raise ImportError(f"cannot load quality gate from {TARGET}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_target = _load_moved_module()

downscale_to_width = _target.downscale_to_width
ink_bbox = _target.ink_bbox
shared_roi_stats = _target.shared_roi_stats
ssim_gray = _target.ssim_gray
stats = _target.stats
main = _target.main

__all__ = ["downscale_to_width", "ink_bbox", "shared_roi_stats", "ssim_gray",
           "stats", "main", "TARGET"]


if __name__ == "__main__":
    raise SystemExit(main())
