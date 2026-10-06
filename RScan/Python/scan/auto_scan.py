"""DEPRECATED MODULE — compatibility shim for ``rscan.scanner``.

Status: **compatibility** (not dead, not canonical).

Historical path of the reference-quality photo scanner. The implementation
now lives in ``rscan/scanner/`` split by responsibility:

    constants.py      all algorithm constants (parity-sensitive)
    preprocessing.py  probe/mask helpers
    geometry.py       corner detection, warp, dewarp, deskew
    photometry.py     illumination flatten + white/black point
    postprocessing.py trims, reframing, binding removal, whitening
    reference.py      bundled reference-page measurement/alignment
    pipeline.py       ``scan_photo_to_reference`` orchestration

This module re-exports the historical public names verbatim, so existing code
and external scripts keep importing them from here. New code should import
from ``rscan.scanner`` instead. Long-form guidance:
``AGENTS.md`` -> "Legacy and compatibility paths".
"""

from __future__ import annotations

try:  # imported as a top-level module: ``python RScan/Python/scan/auto_scan.py``
    from _compat import ensure_project_root_on_path  # noqa: F401
except ModuleNotFoundError:  # imported as ``RScan.Python.scan.auto_scan``
    from ._compat import ensure_project_root_on_path  # type: ignore[no-redef]

ensure_project_root_on_path()

from rscan.scanner.constants import (  # noqa: E402
    DEFAULT_BLACK_POINT,
    DEFAULT_BLACK_POINT2,
    DEFAULT_KSIZE_DIVISOR,
    DEFAULT_SATURATE,
    DEFAULT_WHITE_POINT,
    REF_ASPECT_FALLBACK,
    REF_MARGIN_BOTTOM,
    REF_MARGIN_LEFT,
    REF_MARGIN_RIGHT,
    REF_MARGIN_TOP,
)
from rscan.scanner.geometry import (  # noqa: E402
    deskew,
    dewarp_by_rulings,
    estimate_color_ruling_tilt,
    estimate_skew_angle,
    find_document_contour,
    order_points,
    rectify_from_rulings,
    residual_deskew,
    warp_to_rectangle,
)
from rscan.scanner.photometry import (  # noqa: E402
    auto_black_point,
    black_point_stretch,
    enhance_reference_look,
    high_pass_flatten,
    white_point_stretch,
)
from rscan.scanner.pipeline import scan_photo_to_reference  # noqa: E402
from rscan.scanner.postprocessing import (  # noqa: E402
    auto_trim_margins,
    cut_dark_edge_bands,
    edge_darkness_profile,
    reframe_like_reference,
    remove_binding_rings,
    trim_coil_margin,
    trim_smeared_top_band,
    trim_white_fill_bands,
    whiten_border_artifacts,
    whiten_corner_smears,
)
from rscan.scanner.reference import (  # noqa: E402
    REF_ASPECT,
    align_to_reference_template,
    measure_reference_aspect,
    measure_reference_size,
)

__all__ = [
    "DEFAULT_WHITE_POINT",
    "DEFAULT_BLACK_POINT",
    "DEFAULT_BLACK_POINT2",
    "DEFAULT_SATURATE",
    "DEFAULT_KSIZE_DIVISOR",
    "REF_MARGIN_LEFT",
    "REF_MARGIN_RIGHT",
    "REF_MARGIN_TOP",
    "REF_MARGIN_BOTTOM",
    "REF_ASPECT",
    "REF_ASPECT_FALLBACK",
    "order_points",
    "find_document_contour",
    "warp_to_rectangle",
    "dewarp_by_rulings",
    "rectify_from_rulings",
    "estimate_color_ruling_tilt",
    "estimate_skew_angle",
    "deskew",
    "residual_deskew",
    "high_pass_flatten",
    "white_point_stretch",
    "black_point_stretch",
    "auto_black_point",
    "enhance_reference_look",
    "trim_white_fill_bands",
    "trim_smeared_top_band",
    "edge_darkness_profile",
    "cut_dark_edge_bands",
    "reframe_like_reference",
    "trim_coil_margin",
    "auto_trim_margins",
    "remove_binding_rings",
    "whiten_corner_smears",
    "whiten_border_artifacts",
    "measure_reference_size",
    "measure_reference_aspect",
    "align_to_reference_template",
    "scan_photo_to_reference",
]
