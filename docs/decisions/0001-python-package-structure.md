# ADR 0001 — Adopt an explicit `rscan` Python package

* Status: accepted
* Date: 2026-10-06

## Context

Everything server-side lived in `app.py` (routes, jobs, SSE, temp files) and
`RScan/Python/scan/` (`auto_scan.py` with the whole scanner, `scan_pdf.py` with
PDF processing). Imports relied on `sys.path.insert(...)`, so modules could not
be imported normally, tests were hard to place, and every layer (HTTP, jobs,
scanner, PDF, storage) was reachable from every other.

## Decision

Move the implementation into a top-level `rscan` package with one concern per
module, and keep the old paths as thin, documented compatibility shims:

```
rscan/{config,web,services,jobs,storage,scanner,pdf}
app.py            -> create_app() + dev server
api/index.py      -> WSGI app for Vercel (only sys.path user)
RScan/Python/scan -> compat shims (auto_scan, scan_pdf CLI, scan, quality_gate)
```

Rules that came with it: routes are validate → service → response; `scanner`
and `pdf` never import Flask; configuration is centralised in
`rscan/config/settings.py`; the compatibility shims are explicitly documented in
`AGENTS.md` §16.

## Consequences

* Positive: modules are importable/testable without path hacks; the dependency
  direction is enforceable; new contributors (human or AI) can navigate by
  module name.
* Positive: the CLI and legacy import paths keep working through shims.
* Negative: two module trees exist (canonical + compat), so a reader can land on
  a shim first. Mitigated by loud docstrings and the AGENTS.md table.
* Neutral: `auto_scan.py` had to be split by responsibility; behaviour was
  verified byte-for-byte against fixtures generated from the pre-refactor code.
