"""Vercel serverless entrypoint (@vercel/python).

Vercel imports this module and exposes its ``app`` object as the WSGI handler
(every path is routed here by ``vercel.json``).

The repository root must be importable for ``rscan`` to resolve. Vercel's
Python builder normally puts the deployment root on ``sys.path`` already, but
the legacy ``builds`` configuration does not guarantee it, so we add it
explicitly here. This is the ONLY place in the codebase that touches
``sys.path``; application code always uses plain ``rscan.*`` imports (see
``AGENTS.md`` -> "Important invariants").
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rscan.web import create_app  # noqa: E402 - after the path bootstrap above

app = create_app()

__all__ = ["app"]
