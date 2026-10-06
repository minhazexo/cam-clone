"""Image scanning endpoint.

    POST /api/scan   multipart ``files[]`` -> {"pages": [...]}

Route body is validate -> service -> respond; every scan rule (dedupe,
extension policy, per-file error entries) lives in
``rscan.services.image_scan_service``.

Response contract (see ``docs/API.md``)::

    {"pages": [{"name": "a.jpg", "id": "ab12cd34ef56", "width": 1240, "height": 1754},
               {"name": "b.png", "error": "…"}]}

``id`` is the key for ``GET /api/image/<id>``.
"""

from __future__ import annotations

from flask import Blueprint, request

from rscan.errors import InvalidUploadError
from rscan.services import image_scan_service
from rscan.web.context import get_context
from rscan.web.responses import json_ok

blueprint = Blueprint("scan", __name__)


@blueprint.post("/api/scan")
def api_scan():
    """Scan one or more uploaded images and return their result descriptors."""
    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        raise InvalidUploadError("No files uploaded")

    context = get_context()
    unique = image_scan_service.dedupe_uploads(files)
    results = image_scan_service.scan_uploads(unique, context.storage, context.settings)
    return json_ok(pages=[page.to_dict() for page in results])


__all__ = ["blueprint"]
