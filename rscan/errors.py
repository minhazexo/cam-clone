"""Application-level error hierarchy.

Why this exists: routes must never leak raw Python/OpenCV stack traces to
clients, and every failure should map to a predictable HTTP status + JSON
shape (``{"error": "<human readable>"}``). Raise one of these from services;
``rscan.web.app_factory`` logs the technical detail server-side and returns
``public_message`` to the caller.

Logging contract: ``logger.exception(...)`` at the raise site (or in the
registered handler) carries the full traceback; the client only sees
``public_message``.
"""

from __future__ import annotations


class RScanError(Exception):
    """Base class for every expected, user-reportable failure."""

    #: HTTP status used when the error escapes to a route.
    http_status: int = 500
    #: Default client-facing message (never contains internals).
    default_message: str = "Scan failed unexpectedly."

    def __init__(self, message: str | None = None) -> None:
        self.public_message = message or self.default_message
        super().__init__(self.public_message)


class InvalidUploadError(RScanError):
    """The request carried no usable file (or an empty/duplicate payload)."""

    http_status = 400
    default_message = "No files uploaded"


class UnsupportedFileTypeError(RScanError):
    """The uploaded extension is not accepted by this endpoint."""

    http_status = 400
    default_message = "Unsupported file type"


class InvalidPageLimitError(RScanError):
    """``page_limit`` was present but not a positive integer."""

    http_status = 400
    default_message = "page_limit must be at least 1"


class ScanProcessingError(RScanError):
    """The image scan pipeline failed for an upload."""

    http_status = 500
    default_message = "Image scan failed"


class PdfProcessingError(RScanError):
    """PDF rendering, page scanning, or PDF assembly failed."""

    http_status = 500
    default_message = "PDF scan failed"


class JobNotFoundError(RScanError):
    """SSE progress was requested for an unknown/expired job id."""

    http_status = 404
    default_message = "Job not found"


class StorageError(RScanError):
    """Reading/writing an artifact failed (disk, permissions, bad name)."""

    http_status = 500
    default_message = "Storage error"


class ResultNotFoundError(RScanError):
    """A generated artifact is no longer on disk (serverless restart)."""

    http_status = 404
    default_message = "not found"


__all__ = [
    "RScanError",
    "InvalidUploadError",
    "UnsupportedFileTypeError",
    "InvalidPageLimitError",
    "ScanProcessingError",
    "PdfProcessingError",
    "JobNotFoundError",
    "StorageError",
    "ResultNotFoundError",
]
