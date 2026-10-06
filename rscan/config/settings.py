"""Centralised runtime configuration.

Everything that used to be an ``os.environ`` lookup or a magic number spread
across ``app.py`` lives here. Import once (``get_settings()`` is cached) and
pass the ``Settings`` object down; do not read ``os.environ`` anywhere else.

Environment variables (all optional — defaults are production-safe):

    PORT             HTTP port for ``python app.py``                  (5000)
    RSCAN_DEBUG      "1" enables debug logging + Flask debug mode     (0)
    RSCAN_UPLOAD_DIR directory for uploaded/scanned artifacts
                     (default: <system temp>/rscan_uploads)
    RSCAN_JOB_TTL    seconds an SSE scan job is kept in memory        (600)

Filesystem paths are resolved from the repository root, never from the
current working directory: serverless runtimes (Vercel) may start the process
elsewhere.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

#: Repository root (``<root>/rscan/config/settings.py`` -> ``<root>``).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Image extensions accepted by every upload endpoint (lowercase, with dot).
DEFAULT_IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
)

#: PDF extension accepted by the PDF endpoints.
DEFAULT_PDF_EXTENSIONS = frozenset({".pdf"})

#: 50 MB request cap locally. Vercel caps request bodies at ~4.5 MB before
#: Flask ever sees them, which is why the on-device path exists.
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean env var; "1"/"true"/"yes" (case-insensitive) are true."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to ``default`` on junk input."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration for one RScan process.

    Attributes are grouped by subsystem; see module docstring for the env
    variables that can override them.
    """

    # -- paths ------------------------------------------------------------
    project_root: Path = PROJECT_ROOT
    template_folder: Path = field(default_factory=lambda: PROJECT_ROOT / "templates")
    static_folder: Path = field(default_factory=lambda: PROJECT_ROOT / "static")
    upload_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("RSCAN_UPLOAD_DIR")
            or os.path.join(tempfile.gettempdir(), "rscan_uploads")
        )
    )

    # -- runtime ----------------------------------------------------------
    debug: bool = field(default_factory=lambda: _env_flag("RSCAN_DEBUG"))
    port: int = field(default_factory=lambda: _env_int("PORT", 5000))
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES

    # -- uploads ----------------------------------------------------------
    allowed_image_extensions: frozenset[str] = DEFAULT_IMAGE_EXTENSIONS
    allowed_pdf_extensions: frozenset[str] = DEFAULT_PDF_EXTENSIONS

    # -- image scan output ------------------------------------------------
    #: JPEG quality for scanned images served back to the browser.
    image_jpeg_quality: int = 95

    # -- server PDF scan --------------------------------------------------
    #: Render DPI for input PDF pages. 200 DPI keeps note-page text crisp
    #: while staying far below the old 300 DPI default in pixels/bytes.
    pdf_dpi: int = 200
    #: JPEG quality for pages embedded in the assembled scanned PDF.
    pdf_jpeg_quality: int = 78
    #: Uniform output page size ("A4"/"Letter") with zero margin (full-bleed).
    pdf_page_size: str = "A4"
    pdf_margin: float = 0.0
    pdf_draw_page_border: bool = True
    #: Upper bound on scan worker threads per PDF job.
    pdf_max_workers: int = 8

    # -- jobs / SSE -------------------------------------------------------
    #: Seconds an in-memory scan job (and its result artifacts) is retained.
    job_ttl_seconds: int = field(default_factory=lambda: _env_int("RSCAN_JOB_TTL", 600))
    #: Seconds between SSE keepalive comments when a job is quiet.
    sse_keepalive_seconds: int = 30

    def is_allowed_image(self, filename: str) -> bool:
        """True when ``filename`` has an accepted image extension."""
        return Path(filename).suffix.lower() in self.allowed_image_extensions

    def is_allowed_pdf(self, filename: str) -> bool:
        """True when ``filename`` has an accepted PDF extension."""
        return Path(filename).suffix.lower() in self.allowed_pdf_extensions


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide ``Settings`` (cached; reset in tests)."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached settings (tests that patch env vars use this)."""
    get_settings.cache_clear()
