"""Image decoding/encoding helpers used by the web layer.

Decoding is EXIF-aware on purpose: phone photos are frequently stored
rotated with an EXIF orientation flag that ``cv.imdecode`` ignores (sideways
scans). Pillow applies the flag via ``exif_transpose``; when Pillow is
unavailable we fall back to ``cv.imdecode``.

Both helpers are total: they return ``None`` instead of raising so callers
can skip an unusable upload without aborting a whole batch.
"""

from __future__ import annotations

import io

import cv2 as cv
import numpy as np


def decode_image_bytes(data: bytes, arr: np.ndarray | None = None):
    """Decode upload bytes to a BGR image, honouring EXIF orientation.

    Args:
        data: raw uploaded bytes.
        arr: optional pre-built ``np.frombuffer(data, uint8)`` (avoids a copy
            when the caller already needed it).

    Returns:
        BGR ``np.ndarray``, or ``None`` when the bytes are not a decodable
        image.
    """
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            return cv.cvtColor(np.asarray(im), cv.COLOR_RGB2BGR)
    except Exception:
        pass
    try:
        if arr is None:
            arr = np.frombuffer(data, dtype=np.uint8)
        return cv.imdecode(arr, cv.IMREAD_COLOR)
    except Exception:
        return None


def encode_jpeg(image: np.ndarray, quality: int = 95):
    """Encode a BGR image as JPEG bytes.

    Returns ``None`` when OpenCV cannot encode the image (callers report a
    per-upload error rather than failing the request).
    """
    ok, buf = cv.imencode(".jpg", image, [int(cv.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return None
    return buf.tobytes()


__all__ = ["decode_image_bytes", "encode_jpeg"]
