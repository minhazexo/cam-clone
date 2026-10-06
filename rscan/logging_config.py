"""Logging setup and module logger conventions.

Conventions (kept deliberately simple so logs stay greppable):

    rscan.web.routes.scan      web layer, one logger per module via __name__
    rscan.services.*           use-cases
    rscan.scanner.*            geometry / photometry pipeline
    rscan.pdf.*                PDF rendering + assembly
    rscan.jobs.*               job store + background worker
    rscan.storage.*            artifact storage

Rules:
    * Never use ``print()`` for production behaviour (CLI tools may, but they
      print user-facing results, not diagnostics).
    * Background PDF jobs must log with their ``job_id`` every time.
    * ``configure_logging()`` is called once by the app factory; library code
      only ever calls ``logging.getLogger(__name__)``.
"""

from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(debug: bool = False) -> None:
    """Configure root logging once, at the level the settings request.

    ``debug=True`` turns on DEBUG (verbose Flask/OpenCV logs); otherwise INFO.
    Calling this repeatedly is safe — ``basicConfig`` only configures handlers
    the first time, and the root level is updated explicitly.
    """
    level = logging.DEBUG if debug else logging.INFO
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level, format=_LOG_FORMAT)
    logging.getLogger().setLevel(level)
    # OpenCV/NumPy are chatty under DEBUG in ways that drown out our own logs.
    if not debug:
        for noisy in ("matplotlib", "PIL"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


__all__ = ["configure_logging"]
