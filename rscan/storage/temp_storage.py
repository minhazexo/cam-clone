"""Filesystem-backed storage under one directory.

Used for both local development and serverless deployments:

    * local: the directory lives for the process lifetime, so downloads work
      until the OS clears the temp dir;
    * Vercel: ``/tmp`` is writable but ephemeral and per-instance, so a scan
      result may not be readable by a later request. The API already treats
      result serving as best-effort (HTTP 404 -> the client can re-scan).

Nothing here is concurrency-aware beyond "writes are atomic-ish" (write to a
temp name, then ``os.replace``), which is enough for the UUID-per-artifact
naming used across RScan.
"""

from __future__ import annotations

import os
from pathlib import Path

from rscan.errors import ResultNotFoundError, StorageError
from rscan.storage.file_storage import sanitize_name


class LocalTempStorage:
    """``Storage`` implementation rooted at a single directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - environment failure
            raise StorageError(f"cannot create storage directory: {exc}") from exc

    # -- interface --------------------------------------------------------
    def save(self, name: str, data: bytes) -> Path:
        """Atomically write ``data`` to ``name`` and return its path."""
        target = self._path_for(sanitize_name(name))
        tmp = target.with_name(f".{target.name}.part")
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, target)
        except OSError as exc:
            raise StorageError(f"cannot write artifact: {exc}") from exc
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:  # pragma: no cover - cleanup only
                    pass
        return target

    def read(self, name: str) -> bytes:
        """Return the bytes stored under ``name``."""
        try:
            return self.path(name).read_bytes()
        except OSError as exc:
            raise StorageError(f"cannot read artifact: {exc}") from exc

    def exists(self, name: str) -> bool:
        """True when ``name`` is present (invalid names count as absent)."""
        try:
            return self._path_for(sanitize_name(name)).is_file()
        except StorageError:
            return False

    def delete(self, name: str) -> None:
        """Remove ``name`` if present; missing files are not an error."""
        try:
            self._path_for(sanitize_name(name)).unlink(missing_ok=True)
        except (OSError, StorageError):  # pragma: no cover - cleanup only
            pass

    def path(self, name: str) -> Path:
        """Return the on-disk path for ``name``.

        Raises:
            ResultNotFoundError: when the artifact is not on disk.
        """
        target = self._path_for(sanitize_name(name))
        if not target.is_file():
            raise ResultNotFoundError()
        return target

    def write_path(self, name: str) -> Path:
        """Return a path writers may create; parent dirs exist already."""
        return self._path_for(sanitize_name(name))

    # -- internals --------------------------------------------------------
    def _path_for(self, name: str) -> Path:
        """Join a sanitised name onto the root (caller sanitises first)."""
        candidate = self.root / name
        # Defence in depth: sanitize_name already strips separators, but a
        # resolved-path check keeps any future caller honest.
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("artifact outside storage root") from exc
        return candidate


__all__ = ["LocalTempStorage"]
