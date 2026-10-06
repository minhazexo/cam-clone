"""Liveness probe.

Used by uptime checks, the post-deploy verification step in
``docs/DEPLOYMENT.md``, and the frontend preflight that decides whether the
server PDF flow is available (``static/js/api/health-api.js``).

Response shape is intentionally frozen:

    {"status": "ok", "service": "rscan"}
"""

from __future__ import annotations

from flask import Blueprint

from rscan.web.responses import json_ok

blueprint = Blueprint("health", __name__)


@blueprint.get("/api/health")
def api_health():
    """Return ``{"status": "ok", "service": "rscan"}``."""
    return json_ok(status="ok", service="rscan")


__all__ = ["blueprint"]
