"""Image scan use-case: uploaded image bytes -> stored scanned JPEG.

Flow::

    upload bytes
      -> decode (EXIF aware)
      -> rscan.scanner.pipeline.scan_photo_to_reference
      -> JPEG encode (settings.image_jpeg_quality)
      -> storage.save("<file_id>.jpg")
      -> ScannedImage(name, file_id, width, height)

Behaviour notes kept from the original route (the API contract depends on it):

    * duplicates (same name + size + content type) are collapsed;
    * a PDF in an image batch is a hard 400 — the client must use a PDF flow;
    * unsupported extensions are skipped silently;
    * undecodable images are skipped silently;
    * a pipeline failure becomes a per-file ``error`` entry, not a 500 —
      one bad photo must not lose the rest of the batch.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Optional, Protocol, Sequence, Tuple

from rscan.config import Settings
from rscan.errors import UnsupportedFileTypeError
from rscan.scanner.image_io import decode_image_bytes, encode_jpeg
from rscan.scanner.pipeline import scan_photo_to_reference
from rscan.storage import Storage

logger = logging.getLogger(__name__)


class UploadedFile(Protocol):
    """The subset of Werkzeug's ``FileStorage`` this service needs."""

    filename: str
    content_type: Optional[str]

    def read(self) -> bytes:  # pragma: no cover - protocol declaration
        ...


@dataclass(frozen=True)
class ScannedImage:
    """One scanned page returned to the client."""

    name: str
    file_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """JSON shape of ``GET /api/scan`` entries."""
        if self.error is not None:
            return {"name": self.name, "error": self.error}
        return {"name": self.name, "id": self.file_id,
                "width": self.width, "height": self.height}


def dedupe_uploads(files: Iterable[UploadedFile]) -> List[Tuple[UploadedFile, bytes]]:
    """Read uploads once, dropping empty names and exact duplicates.

    The dedupe signature mirrors the original implementation exactly:
    ``(filename, byte length, content type)``.
    """
    seen = set()
    unique: List[Tuple[UploadedFile, bytes]] = []
    for f in files:
        if f is None or not getattr(f, "filename", ""):
            continue
        data = f.read()
        signature = (f.filename, len(data), f.content_type or "")
        if signature in seen:
            continue
        seen.add(signature)
        unique.append((f, data))
    return unique


def scan_upload(filename: str, data: bytes, storage: Storage,
                settings: Settings) -> Optional[ScannedImage]:
    """Scan one upload and persist the result.

    Returns ``None`` when the upload should be ignored (unsupported
    extension or undecodable bytes), or a ``ScannedImage`` carrying either the
    stored artifact id or a per-file ``error``.

    Raises:
        UnsupportedFileTypeError: when the upload is a PDF (image batches must
            not silently swallow PDFs; the client is told to use a PDF flow).
    """
    if settings.is_allowed_pdf(filename):
        raise UnsupportedFileTypeError(
            "PDF files are processed locally in the browser. Use the PDF scan control."
        )
    if not settings.is_allowed_image(filename):
        logger.info("image scan skipping unsupported extension file=%r", filename)
        return None

    image = decode_image_bytes(data)
    if image is None:
        logger.warning("image scan could not decode file=%r bytes=%d", filename, len(data))
        return None

    try:
        scanned = scan_photo_to_reference(image)
    except Exception as exc:
        logger.exception("image scan failed file=%r error=%s", filename, exc)
        return ScannedImage(name=filename, error=str(exc))

    jpeg = encode_jpeg(scanned, quality=settings.image_jpeg_quality)
    if jpeg is None:
        logger.error("image scan JPEG encode failed file=%r", filename)
        return ScannedImage(name=filename, error="JPEG encode failed")

    file_id = uuid.uuid4().hex[:12]
    storage.save(f"{file_id}.jpg", jpeg)
    logger.info("image scan done file=%r id=%s dims=%dx%d",
                filename, file_id, scanned.shape[1], scanned.shape[0])
    return ScannedImage(name=filename, file_id=file_id,
                        width=int(scanned.shape[1]), height=int(scanned.shape[0]))


def scan_uploads(files: Sequence[Tuple[UploadedFile, bytes]], storage: Storage,
                 settings: Settings) -> List[ScannedImage]:
    """Scan every unique upload, preserving order and per-file failures."""
    results: List[ScannedImage] = []
    for f, data in files:
        scanned = scan_upload(f.filename, data, storage, settings)
        if scanned is not None:
            results.append(scanned)
    return results


__all__ = ["UploadedFile", "ScannedImage", "dedupe_uploads", "scan_upload", "scan_uploads"]
