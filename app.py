"""RScan local entrypoint.

Everything the app does lives in the ``rscan`` package; this file only wires
the process up and runs the development server.

    pip install -r requirements.txt
    python app.py            # -> http://localhost:5000

Environment: PORT (default 5000), RSCAN_DEBUG=1 for verbose logs.
See ``docs/DEPLOYMENT.md`` for the Vercel entrypoint (``api/index.py``) and
``AGENTS.md`` for the architecture map.
"""

from __future__ import annotations

from rscan.config import get_settings
from rscan.web import create_app

#: WSGI callable used by ``flask run``, gunicorn and the test suite.
app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    app.run(
        debug=settings.debug,
        host="0.0.0.0",
        port=settings.port,
        threaded=True,  # required for SSE streaming + background PDF jobs
    )
