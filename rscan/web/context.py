"""Per-app dependency container shared by the factory and the routes.

Kept in its own module so routes can import ``get_context`` without importing
``app_factory`` (which registers those routes) — that would be a cycle.

Why a container at all: routes need settings, storage and the job store; a
module-level global would make tests fight over shared state. Instead
``create_app()`` builds one ``ApplicationContext`` and stores it on
``app.extensions``, so each app instance is isolated.
"""

from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

from rscan.config import Settings
from rscan.jobs.job_store import JobStore
from rscan.storage import Storage

#: Key under which the container is stored on ``app.extensions``.
CONTEXT_KEY = "rscan"


@dataclass(frozen=True)
class ApplicationContext:
    """Collaborators every route needs (settings, storage, jobs)."""

    settings: Settings
    storage: Storage
    job_store: JobStore


def get_context() -> ApplicationContext:
    """Return the ``ApplicationContext`` of the current Flask app.

    Must be called inside a request/app context (routes, CLI, tests).
    """
    return current_app.extensions[CONTEXT_KEY]


__all__ = ["CONTEXT_KEY", "ApplicationContext", "get_context"]
