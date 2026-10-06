"""Server PDF scanning: synchronous scan, background job, SSE progress, download.

    POST /api/scan-pdf                      -> {"pdf": "scanned_ab12cd34.pdf"}
    POST /api/scan-pdf-start                -> {"job_id": "9f8e..."}
    GET  /api/scan-pdf-progress/<job_id>    -> SSE frames (see below)
    GET  /api/pdf/<filename>                -> application/pdf attachment

SSE frames (one JSON object per ``data:`` line)::

    {"type":"loading"}
    {"type":"detected","total":12}
    {"type":"scanning","page":1,"total":12}
    {"type":"page_done","page":1,"total":12}
    {"type":"assembling"}
    {"type":"done","pdf":"scanned_ab12cd34.pdf","elapsed":8.4}
    {"type":"error","message":"…"}
    {"type":"_eof"}                     # stream closing sentinel

The route never scans: it stores the upload, starts
``rscan.jobs.job_worker.start_pdf_scan_job`` and streams the events the job
produces through ``rscan.services.scan_progress_service``.

Validation shared by both POST endpoints lives in the two private helpers
below (request-shape checks only — no scan logic).
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from flask import Blueprint, Response, request, send_file, stream_with_context

from rscan.errors import InvalidUploadError, InvalidPageLimitError, UnsupportedFileTypeError
from rscan.jobs.job_worker import start_pdf_scan_job
from rscan.services import pdf_scan_service, scan_progress_service
from rscan.web.context import get_context
from rscan.web.responses import json_ok

logger = logging.getLogger(__name__)

blueprint = Blueprint("pdf", __name__)


# ── request validation helpers ─────────────────────────────────────────────

def _require_pdf_upload():
    """Return the uploaded PDF ``FileStorage`` or raise a domain error."""
    file = request.files.get("file")
    if not file or file.filename == "":
        raise InvalidUploadError("No file uploaded")
    if not get_context().settings.is_allowed_pdf(file.filename):
        raise UnsupportedFileTypeError("Only PDF files are accepted")
    return file


def _parse_page_limit() -> Optional[int]:
    """Parse the optional ``page_limit`` form field (None means "all pages")."""
    page_limit = request.form.get("page_limit", type=int)
    if page_limit is not None and page_limit < 1:
        raise InvalidPageLimitError("page_limit must be at least 1")
    return page_limit


# ── routes ─────────────────────────────────────────────────────────────────

@blueprint.post("/api/scan-pdf")
def api_scan_pdf():
    """Scan a PDF synchronously and return the downloadable filename."""
    file = _require_pdf_upload()
    page_limit = _parse_page_limit()

    context = get_context()
    in_name = f"in_{uuid.uuid4().hex[:8]}.pdf"
    out_name = f"scanned_{uuid.uuid4().hex[:8]}.pdf"
    in_path = context.storage.save(in_name, file.read())
    logger.info("scan-pdf received file=%s page_limit=%s", file.filename, page_limit)

    try:
        pdf_scan_service.scan_pdf_file(
            str(in_path),
            str(context.storage.write_path(out_name)),
            page_limit,
            context.settings,
        )
    finally:
        context.storage.delete(in_name)

    return json_ok(pdf=out_name)


@blueprint.post("/api/scan-pdf-start")
def api_scan_pdf_start():
    """Store the upload, start a background scan, return its ``job_id``."""
    context = get_context()
    context.job_store.cleanup()

    file = _require_pdf_upload()
    page_limit = _parse_page_limit()

    data = file.read()
    in_name = f"in_{uuid.uuid4().hex[:8]}.pdf"
    in_path = context.storage.save(in_name, data)

    job = context.job_store.create()
    logger.info("scan-pdf-start job_id=%s file=%s bytes=%d",
                job.id, file.filename, len(data))
    start_pdf_scan_job(job.id, in_path, file.filename, page_limit,
                       context.settings, context.job_store, context.storage)
    return json_ok(job_id=job.id)


@blueprint.get("/api/scan-pdf-progress/<job_id>")
def api_scan_pdf_progress(job_id: str):
    """Stream a job's progress as Server-Sent Events."""
    context = get_context()
    frames = scan_progress_service.stream_job(
        job_id, context.job_store,
        keepalive_seconds=context.settings.sse_keepalive_seconds,
    )
    return Response(
        stream_with_context(frames),
        headers=scan_progress_service.SSE_HEADERS,
    )


@blueprint.get("/api/pdf/<filename>")
def api_pdf(filename: str):
    """Serve a scanned PDF as a download attachment."""
    if os.path.basename(filename) != filename or not filename.startswith("scanned_"):
        return "not found", 404
    context = get_context()
    if not context.storage.exists(filename):
        return "not found", 404
    return send_file(context.storage.path(filename), mimetype="application/pdf",
                     as_attachment=True, download_name=filename)


__all__ = ["blueprint"]
