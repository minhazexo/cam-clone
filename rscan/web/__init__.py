"""Web layer — Flask application factory, routes and response helpers.

    from rscan.web import create_app
    app = create_app()

Layering: this package is the only place that knows about Flask, requests and
HTTP status codes. Routes validate input, call a service, and return a
response — no OpenCV, no threads, no file handling.

    app_factory.py   create_app() + error handlers
    context.py       the per-app ApplicationContext (settings/storage/jobs)
    responses.py     JSON helpers shared by every route
    routes/          one blueprint module per API surface
"""

from rscan.web.app_factory import create_app
from rscan.web.context import ApplicationContext, get_context

__all__ = ["ApplicationContext", "create_app", "get_context"]
