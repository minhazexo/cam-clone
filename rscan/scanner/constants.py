"""Scanner algorithm constants — the single source of truth.

Every value here is part of the Python <-> JavaScript/WASM parity contract
(the JS mirror lives in ``static/js/workers/scan-worker-v2.js`` and
``scan-geometry.js``). Changing a value here without mirroring it there will
break ``bun run parity``; the docstring on each constant says what it does and
whether it is parity-sensitive.

Origin: these defaults come from the original RScan GCMODE pipeline
(``sourabhkhemka/DocumentScanner``) and were carried over unchanged when the
web product and the reference-look photometry were added.
"""

from __future__ import annotations

# ── Photometry (original RScan GCMODE defaults, parity-sensitive) ──────────

#: Highlights above this are truncated, then [0, wp] is stretched to [0, 255].
#: 127 == pure mid-gray, which is what makes the reference background white.
DEFAULT_WHITE_POINT = 127

#: First black-point stretch: (img - bp) * 255 / (255 - bp). Pushes ink dark.
DEFAULT_BLACK_POINT = 66

#: Second black-point stretch (same math, smaller value) run after the first;
#: the pair is what gives reference-quality deep blacks without clipping noise.
DEFAULT_BLACK_POINT2 = 20

#: Slight chroma boost around luminance so colored ink (blue headings, pink
#: rulings) survives white-point stretching. 1.0 == off.
DEFAULT_SATURATE = 1.25

#: Illumination-flatten kernel: ksize = min(h, w) // divisor, forced odd and
#: clamped to [KERNEL_MIN_SIZE, KERNEL_MAX_SIZE]. 8 tuned against the
#: reference photos; larger divisor == smaller kernel == more local flatten.
DEFAULT_KSIZE_DIVISOR = 8
KERNEL_MIN_SIZE = 21
KERNEL_MAX_SIZE = 101

# ── Reference framing (measured from the bundled reference page) ───────────
# Symmetric-ish margins of the reference page. The originals were too loose
# for notebook pages and left extra whitespace; these match reference.png.
REF_MARGIN_LEFT = 0.069
REF_MARGIN_RIGHT = 0.071
REF_MARGIN_TOP = 0.070
REF_MARGIN_BOTTOM = 0.040

#: Fallback aspect ratio (width / height) used only when the bundled
#: ``Work Images/reference.png`` is unavailable (CI, installed copies).
#: Parity-sensitive: the JS worker hardcodes the same fraction.
REF_ASPECT_FALLBACK = 893.0 / 1263.0

# ── Pipeline defaults ─────────────────────────────────────────────────────

#: Default upscale of the final scan (reference.png is ~2x the wiki photo).
#: Server image scans keep 2.0; PDF page scans pass output_scale=1.0 because
#: the 200-DPI render is already the target resolution and the upscale only
#: blurs text edges while quadrupling pixels.
DEFAULT_OUTPUT_SCALE = 2.0

__all__ = [
    "DEFAULT_WHITE_POINT",
    "DEFAULT_BLACK_POINT",
    "DEFAULT_BLACK_POINT2",
    "DEFAULT_SATURATE",
    "DEFAULT_KSIZE_DIVISOR",
    "KERNEL_MIN_SIZE",
    "KERNEL_MAX_SIZE",
    "REF_MARGIN_LEFT",
    "REF_MARGIN_RIGHT",
    "REF_MARGIN_TOP",
    "REF_MARGIN_BOTTOM",
    "REF_ASPECT_FALLBACK",
    "DEFAULT_OUTPUT_SCALE",
]
