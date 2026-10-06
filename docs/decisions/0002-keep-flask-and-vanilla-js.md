# ADR 0002 — Keep Flask and vanilla JavaScript

* Status: accepted
* Date: 2026-10-06

## Context

The refactor goal was clarity and maintainability. Two migrations were
considered and rejected: Flask → FastAPI, and vanilla JS → a component
framework.

## Decision

Keep Flask (3.x), plain ES modules in the browser, Bun only for vendoring
(`runtime.js`, `pdf.worker.js`) and for tests, and OpenCV as the CV engine.

Rationale:

* The HTTP surface is nine endpoints with one streaming case (SSE) that the
  current threading model already handles.
* The frontend is two server-rendered pages with a shared DOM shell; a build
  step and component runtime would add tooling without removing any logic.
* The scanner is the product. Migrating frameworks would touch everything
  except the part that actually matters, while risking the Python↔JS parity
  contract.
* The on-device path must stay dependency-light: pdf.js (vendored), OpenCV.js
  (vendored), pdf-lib (vendored). A framework bundle would be a third large
  download.

## Consequences

* Positive: zero build step for application code; `python app.py` just runs;
  Vercel deploys without a build command.
* Positive: parity is verifiable in plain Node.
* Negative: no framework ergonomics — state and DOM wiring are explicit. This is
  mitigated by `core/` (constants, state, DOM helpers), `ui/` controllers, and
  the documented id contract in `docs/FRONTEND_ARCHITECTURE.md`.
* Revisit if: the UI grows to multiple routes with shared interactive state, or
  the API grows beyond a handful of resources.
