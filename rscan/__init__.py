"""RScan — smart document scanner (Python backend).

This package contains every piece of server-side logic. It is a plain Python
package: import it as ``rscan.*`` from the repository root, never through
``sys.path`` manipulation (see ``api/index.py`` for the single documented
serverless exception).

Package map (dependency direction: web -> services -> domain -> storage):

    rscan.config            centralised configuration (env vars, limits)
    rscan.errors            application-level error hierarchy
    rscan.logging_config    logging setup + module logger conventions
    rscan.storage           file storage abstraction (temp/serverless aware)
    rscan.scanner           document-scan domain: geometry + photometry pipeline
    rscan.pdf               PDF domain: page rendering + scanned-PDF assembly
    rscan.jobs              job state + background worker + progress events
    rscan.services          use-cases that orchestrate the domain layers
    rscan.web               Flask application factory, routes, responses

Layering rules:
    * ``rscan.scanner`` and ``rscan.pdf`` must never import Flask or HTTP code.
    * ``rscan.web`` routes must not contain business logic (validate -> service
      -> response only).
    * ``rscan.services`` orchestrates domain + storage; it does not know about
      Flask request objects either.

See ``docs/ARCHITECTURE.md`` and ``AGENTS.md`` for the full written contract.
"""
