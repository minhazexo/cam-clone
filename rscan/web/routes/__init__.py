"""HTTP routes, grouped by API surface.

    health.py   GET /api/health                     liveness probe
    pages.py    GET /, /scan-pdf                    HTML pages
    scan.py     POST /api/scan                      image scanning
    pdf.py      POST /api/scan-pdf,
                POST /api/scan-pdf-start,
                GET  /api/scan-pdf-progress/<id>,   server PDF flow
                GET  /api/pdf/<filename>
    images.py   GET /api/image/<id>                 scanned image download

Each module defines a Flask ``Blueprint`` and nothing else; adding an endpoint
means adding a route function that validates, calls a service, and returns a
response (see ``AGENTS.md`` -> "How to add a new API endpoint").
"""

from __future__ import annotations

from flask import Flask

from rscan.web.routes import health, images, pages, pdf, scan

#: Registration order defines the order routes appear in ``app.url_map``.
BLUEPRINTS = (pages.blueprint, health.blueprint, scan.blueprint, pdf.blueprint,
              images.blueprint)


def register_blueprints(app: Flask) -> None:
    """Register every route blueprint on ``app``."""
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)


__all__ = ["BLUEPRINTS", "register_blueprints"]
