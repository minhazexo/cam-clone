"""Scanned image download.

    GET /api/image/<file_id>   -> image/jpeg

``file_id`` is the id returned by ``POST /api/scan``. Serving is best-effort:
on serverless the artifact may have been evicted with its instance, in which
case the client gets a 404 and can re-scan. The response for a missing file is
plain text ``not found`` (unchanged from the original implementation, and the
frontend only ever treats it as a failed image load).
"""

from __future__ import annotations

from flask import Blueprint, send_file

from rscan.web.context import get_context

blueprint = Blueprint("images", __name__)


@blueprint.get("/api/image/<file_id>")
def api_image(file_id: str):
    """Serve a scanned image by its id."""
    context = get_context()
    name = f"{file_id}.jpg"
    if not context.storage.exists(name):
        return "not found", 404
    return send_file(context.storage.path(name), mimetype="image/jpeg")


__all__ = ["blueprint"]
