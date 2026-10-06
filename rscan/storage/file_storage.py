"""Storage interface used by services and routes.

``Storage`` is intentionally tiny (save/read/exists/delete/path): enough to
keep file handling out of the scan logic, not an ORM. Implementations own
naming, sanitisation and (for temp storage) cleanup.

Contract:
    * names are flat identifiers ("ab12cd34ef.jpg"), never paths;
    * every method raises ``StorageError`` on unexpected failures;
    * ``path()`` may raise ``ResultNotFoundError`` when the artifact is gone
      (serverless instances are recycled between the scan and the download).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from rscan.errors import StorageError

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_name(name: str) -> str:
    """Return a safe flat artifact name.

    Collapses anything that is not ``[A-Za-z0-9._-]`` to ``_``, strips path
    separators and leading dots, and rejects empty/relative results so a
    crafted URL can never escape the storage root.

    Raises:
        StorageError: if nothing usable is left after sanitisation.
    """
    cleaned = _UNSAFE_RE.sub("_", str(name or "")).lstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise StorageError("invalid artifact name")
    return cleaned


@runtime_checkable
class Storage(Protocol):
    """Flat artifact storage (bytes in, bytes out)."""

    def save(self, name: str, data: bytes) -> Path:
        """Write ``data`` under ``name`` and return the resulting path."""

    def read(self, name: str) -> bytes:
        """Return the bytes stored under ``name``; raises on missing."""

    def exists(self, name: str) -> bool:
        """True when an artifact called ``name`` is present."""

    def delete(self, name: str) -> None:
        """Delete ``name`` if present (never raises for missing files)."""

    def path(self, name: str) -> Path:
        """Return the on-disk path for ``name``; raises if missing."""

    def write_path(self, name: str) -> Path:
        """Return a filesystem path that may be written to as ``name``.

        Needed by writers that take a path instead of bytes (PyMuPDF saves a
        PDF by filename). The file does not have to exist yet.
        """


__all__ = ["Storage", "sanitize_name"]
