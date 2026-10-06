"""Scanner domain — the document-scan pipeline (pure OpenCV + NumPy).

Module map (a reader should be able to stop after this list):

    constants.py       every algorithm constant, with parity notes
    preprocessing.py   scale-invariant grayscale probe + ink mask
    geometry.py        corner detection, warp, ruling-based dewarp, deskew
    photometry.py      illumination flatten, white/black point, saturation
    postprocessing.py  trims, reframing, binding removal, border whitening
    reference.py       bundled reference-template measurement + alignment
    image_io.py        bytes -> BGR decode (EXIF aware) and JPEG encode
    pipeline.py        orchestration: scan_photo_to_reference()

Hard rules for this package:
    * No Flask, no HTTP, no file paths from the caller, no globals beyond the
      immutable reference measurement cache.
    * Behaviour must stay bit-compatible with the JavaScript port in
      ``static/js/workers/`` (see ``docs/SCAN_PIPELINE.md``). Any change to
      numbers in these modules must be mirrored there and re-verified with
      ``bun run parity``.
"""

from rscan.scanner.pipeline import scan_photo_to_reference

__all__ = ["scan_photo_to_reference"]
