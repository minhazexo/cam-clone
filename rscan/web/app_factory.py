"""Flask application factory.

``create_app()`` is the only place where settings, storage and the job store
are constructed, so swapping an implementation (e.g. a Redis-backed job
store) is a one-line change here and nothing else.

Template/static folders are absolute (from ``rscan.config``) because
serverless runtimes may run the process from a different working directory.

Error handling:
    * ``RScanError`` subclasses -> logged server-side, returned as
      ``{"error": public_message}`` with the class's ``http_status``;
    * unexpected exceptions -> full traceback logged, generic message out;
    * ``HTTPException`` under ``/api/*`` -> JSON body instead of Flask HTML,
      so API clients get one error shape;
    * page routes keep Flask's default HTML error pages.
"""

from __future__ import annotations

import logging

from flask import Flask, request
from werkzeug.exceptions import HTTPException

from rscan.config import Settings, get_settings
from rscan.errors import RScanError
from rscan.jobs.job_store import JobStore
from rscan.logging_config import configure_logging
from rscan.storage import LocalTempStorage
from rscan.web.context import CONTEXT_KEY, ApplicationContext
from rscan.web.responses import json_error
from rscan.web.routes import register_blueprints

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> Flask:
    """Build the RScan Flask application.

    Args:
        settings: override the process settings (tests pass a custom
            ``upload_dir``; production uses the cached ``get_settings()``).

    Returns:
        A configured ``Flask`` app with all blueprints and error handlers
        registered.
    """
    settings = settings or get_settings()
    configure_logging(settings.debug)

    app = Flask(
        __name__,
        template_folder=str(settings.template_folder),
        static_folder=str(settings.static_folder),
    )
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_bytes

    context = ApplicationContext(
        settings=settings,
        storage=LocalTempStorage(settings.upload_dir),
        job_store=JobStore(ttl_seconds=settings.job_ttl_seconds),
    )
    app.extensions[CONTEXT_KEY] = context

    register_blueprints(app)
    _register_error_handlers(app)

    logger.info("rscan app created debug=%s storage=%s templates=%s",
                settings.debug, context.storage.root, settings.template_folder)
    return app


def _register_error_handlers(app: Flask) -> None:
    """Attach the shared error-to-response translation."""

    @app.errorhandler(RScanError)
    def _handle_rscan_error(exc: RScanError):
        logger.warning("request failed path=%s status=%d error=%s",
                       request.path, exc.http_status, exc.public_message)
        return json_error(exc.public_message, exc.http_status)

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException):
        # API clients get JSON; page routes keep Flask's HTML pages.
        if request.path.startswith("/api/"):
            return json_error(exc.description or exc.name, exc.code or 500)
        return exc

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        if isinstance(exc, HTTPException):
            return exc
        logger.exception("unhandled error path=%s error=%s", request.path, exc)
        return json_error("Internal server error", 500)


__all__ = ["create_app"]
