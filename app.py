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

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if "rscan" not in os.listdir(_ROOT):
    # Local Windows checkout only (Vercel/Linux are case-sensitive and always
    # take the fast path above): the repo holds both `rscan/` (this app) and
    # `RScan/` (legacy shims), which collapse into ONE directory on a
    # case-insensitive filesystem, so `import rscan` fails even though the
    # files are on disk. Alias the on-disk directory as `rscan`; every
    # submodule name is lowercase-exact, so `rscan.*` imports then resolve
    # normally. `api/index.py` (Vercel) is intentionally left untouched.
    for _entry in os.listdir(_ROOT):
        if _entry.lower() == "rscan":
            import importlib.util

            _pkg_dir = os.path.join(_ROOT, _entry)
            _spec = importlib.util.spec_from_file_location(
                "rscan",
                os.path.join(_pkg_dir, "__init__.py"),
                submodule_search_locations=[_pkg_dir],
            )
            if _spec is None or _spec.loader is None:
                raise ImportError("Cannot bootstrap the rscan package on this checkout.")
            _pkg = importlib.util.module_from_spec(_spec)
            sys.modules["rscan"] = _pkg
            _spec.loader.exec_module(_pkg)
            break

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
