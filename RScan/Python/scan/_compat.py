"""Path bootstrap for the legacy compatibility modules in this directory.

Canonical scanner code lives in the ``rscan`` package (``rscan/scanner/``,
``rscan/pdf/``). This directory keeps thin shims so older commands keep
working:

    python RScan/Python/scan/scan_pdf.py in.pdf out.pdf

Running a script by path puts *its own directory* on ``sys.path[0]``, so the
repository root is missing and ``import rscan`` would fail. That is the only
reason this file exists — application code never manipulates ``sys.path``.
"""

from __future__ import annotations

import os
import sys

#: <root>/RScan/Python/scan/_compat.py -> <root>
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def ensure_project_root_on_path() -> str:
    """Add the repository root to ``sys.path`` (idempotent); return it."""
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    return PROJECT_ROOT


__all__ = ["PROJECT_ROOT", "ensure_project_root_on_path"]
