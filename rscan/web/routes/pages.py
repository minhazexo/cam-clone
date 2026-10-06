"""HTML page routes.

    GET /           main product page: images + server PDF scan
    GET /scan-pdf   on-device PDF scan page (WASM engine, nothing uploaded)

``active_page`` drives the header nav highlight in
``templates/layouts/base.html``.
"""

from __future__ import annotations

from flask import Blueprint, render_template

blueprint = Blueprint("pages", __name__)


@blueprint.get("/")
def index():
    """Render the main scanner page."""
    return render_template(
        "index.html",
        active_page="images",
        tagline="Smart Document Scanner \u2014 Like CamScanner",
    )


@blueprint.get("/scan-pdf")
def scan_pdf_page():
    """Render the on-device full-quality PDF scan page."""
    return render_template(
        "scan_pdf.html",
        active_page="pdf",
        tagline="On-device full-quality scan \u2014 engine loads once, then unlimited pages, no upload",
    )


__all__ = ["blueprint"]
