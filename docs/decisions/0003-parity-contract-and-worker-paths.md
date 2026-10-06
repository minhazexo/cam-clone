# ADR 0003 — Treat parity, worker paths and template ids as contracts

* Status: accepted
* Date: 2026-10-06

## Context

Three couplings are invisible in the source but expensive to break:

1. **Python ↔ JavaScript scanner parity.** The browser pipeline
   (`static/js/workers/`) mirrors the Python pipeline numerically. Nothing in
   the type system enforces it.
2. **Worker and vendor asset paths.** `/static/js/workers/scan-worker-v2.js`,
   `/static/vendor/opencv.js`, `/static/vendor/pdf.worker.js` are referenced by
   the frontend constants, `importScripts`, the templates, and the Node parity
   harnesses.
3. **Template element ids.** `uploadZone`, `stepLog`, `resultsGrid`, … are
   looked up by the frontend modules with no compile-time link.

## Decision

Make each coupling explicit and testable:

* Parity: three Node harnesses (`tests/parity/*`) gate the JS output against
  committed fixtures produced by Python (MAD ≤ 3.0, exact dimensions, tilt and
  sharpness windows). Fixture regeneration is an intentional, reviewed act.
* Paths: one constants module on each side (`static/js/core/constants.js`,
  `rscan/config/settings.py`) plus `bun run check` and
  `tests/js/assets.test.js`, which fail if a referenced asset is missing.
* Ids: `templates/partials/*` documents the contract, the integration tests
  assert the ids are present in rendered HTML, and
  `docs/FRONTEND_ARCHITECTURE.md` lists which module owns which element.

## Consequences

* Positive: a path/rename mistake or a scanner drift fails in CI, not in the
  browser.
* Positive: moving a worker requires updating exactly four places (constants,
  `importScripts`, templates, tests) — and the tests say so.
* Negative: fixtures are ~10 MB of committed binary data, and the parity suite
  must be run for any scanner change. Accepted: it is the only regression
  protection for the product's core value.
* Negative: renaming a template id is a multi-file change. Accepted: the ids are
  already a de-facto API for the frontend.
