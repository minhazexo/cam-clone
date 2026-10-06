# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed — parallel PDF page scanning

Selecting a PDF no longer scans strictly one page at a time:

- **Worker pool (on-device).** `/scan-pdf` scans
  `min(pages, cap, usableCores(hardwareConcurrency))` pages concurrently —
  `cap` 6 on desktop and 3 on small screens; below 8 cores every core scans
  (`usableCores` reserves one core only when there is a spare to give) — using
  lazily-warmed spare OpenCV.js workers (`engine-loader.acquirePool`). A
  single-page PDF, a single CPU core and the home page's `fallback` profile
  keep the previous single-worker behaviour, and a spare worker that fails to
  warm up simply shrinks the pool.
- **The pool reason is shown in the UI.** `scanPoolPlan` returns the chosen
  size *and* the constraint that bounded it (`only N pages`, `N cores`,
  `memory cap`, `small screen`, `single CPU core`, …); the scan panel logs
  e.g. `Engine worker ready (v2-full) — 6 pages at once (memory cap)` and
  `Page N of X scanned` per page, so a smaller-than-expected pool is never a
  mystery.
- **Chunked pipeline with overlap.** Each chunk is rendered together (pdf.js
  works off the main thread), scanned with one worker per page, then appended
  strictly in document order with each canvas released as soon as it is
  embedded — while the *next* chunk's render+scan already runs on the pool
  (the previous chunk's scan completes before the next is sent, so one
  in-flight message per worker still holds). The PDF's page order and layout
  are unchanged, and memory stays bounded to two chunks of canvases.
- **Non-blocking JPEG encode.** `canvas.toBlob` + `arrayBuffer()` replaces the
  synchronous `toDataURL` + base64-decode loop (same encoder, same quality),
  and the results-grid thumbnail is only encoded when it will be kept.
- **Server sync endpoint parallelised.** `POST /api/scan-pdf` now shares
  `scan_pages_parallel` with the background job. The worker bound is
  affinity-aware (`sched_getaffinity`, falling back to `os.cpu_count()`), so a
  container restricted to fewer CPUs no longer builds a pool it cannot run.

Per-page work is untouched: no scanner constant, operation order or worker
message changed, and `bun run parity` passes at the original gates.

### Changed — architecture refactor (behaviour-preserving)

The product behaves the same; the code is organised into layers with explicit
boundaries. Scan output was verified byte-identical to the previous pipeline on
the committed parity fixtures.

- **Python package structure.** Server code now lives in the `rscan` package:
  `config/`, `web/` (factory, context, routes), `services/`, `jobs/`,
  `storage/`, `scanner/`, `pdf/`. `app.py` is a thin local entrypoint and
  `api/index.py` a thin Vercel entrypoint.
- **`sys.path` hacks removed** from application code. `api/index.py` keeps a
  single documented bootstrap for Vercel; the legacy modules under
  `RScan/Python/scan/` keep a compat helper so old commands still run.
- **Scanner split by responsibility**: `constants.py`, `preprocessing.py`,
  `geometry.py`, `photometry.py`, `postprocessing.py`, `reference.py`,
  `image_io.py`, and an orchestration-only `pipeline.py` (previously one
  1314-line `auto_scan.py`).
- **PDF layer extracted**: `rscan/pdf/{renderer,assembler,pdf_service}.py` and
  `rscan/services/pdf_scan_service.py` (sync + streaming) instead of one
  `scan_pdf.py`.
- **Jobs and SSE extracted**: `rscan/jobs/{job_store,job_worker,events}.py` plus
  `rscan/services/scan_progress_service.py`; the SSE route now only translates
  job events into frames.
- **Storage abstraction**: `rscan/storage/` (`Storage` protocol +
  `LocalTempStorage`) with artifact-name sanitisation.
- **Configuration centralised** in `rscan/config/settings.py` (limits, DPI,
  JPEG quality, page size, job TTL, keepalive, allowed extensions).
- **Typed error hierarchy** (`rscan/errors.py`) with HTTP status mapping; API
  errors are always `{"error": "…"}` and never leak tracebacks.
- **Frontend modularised** without a framework: `static/js/{core,api,ui,features}`
  with one constants module (limits, endpoints, asset paths, PDF profiles).
  `app.js` and `scanpdf.js` are now composition-root entrypoints; the duplicated
  UI/progress/modal/results code they shared is consolidated in `ui/`.
- **Worker layer consolidated** under `static/js/workers/`
  (`scan-worker.js`, `scan-worker-v2.js`, `scan-geometry.js`, new
  `engine-loader.js` replacing `opencv-loader.js`).
- **Templates** now use a layout (`templates/layouts/base.html`) plus shared
  partials (processing panel, results panel, page-limit modal, footer) instead
  of three copies of the same markup.
- **Tests reorganised**: `tests/unit/` (settings, storage, jobs, scanner, PDF),
  `tests/integration/` (every API flow through the Flask test client),
  `tests/js/` (helpers + asset/import contracts), `tests/parity/` (unchanged
  harnesses, new paths).
- **Docs added**: `AGENTS.md` (AI-facing map + CHANGE MAP), `docs/ARCHITECTURE.md`,
  `docs/API.md`, `docs/SCAN_PIPELINE.md`, `docs/PDF_PIPELINE.md`,
  `docs/FRONTEND_ARCHITECTURE.md`, `docs/TESTING.md`, `docs/DEPLOYMENT.md`,
  `docs/AI_CONTEXT.md`, and three ADRs in `docs/decisions/`.
- **Tooling**: `bun run test` runs the whole suite; `scripts/check.ts` asserts
  the new asset contract; CI now has separate frontend, parity and backend jobs;
  `.github/CODEOWNERS` marks the parity-sensitive paths.

### Fixed

- `docs/` is committed again (it was previously git-ignored, which hid project
  documentation from the repository).
- `.gitignore` no longer hides real files: the scratch-file patterns are now
  anchored to the repository root, so `scripts/quality_gate.py` and
  `RScan/Python/scan/scan.py` are tracked.
- Artifact serving goes through the storage layer, so crafted names cannot
  escape the storage root.

### Notes

- No API shape, status code, limit, or scan-output change is intended. See
  `docs/API.md` for the documented contract (including the behaviour that a
  `.pdf`-named file which is not a real PDF returns a 500 processing error).

## [0.2.0] — 2026-09-23

### Added

- On-device full-quality scan page `/scan-pdf` (pdf.js → OpenCV.js worker → pdf-lib) with server-parity output (MAD ≤ 0.05).
- Page-limit picker (10–50 / All) on both scan pages; local caps 250 MB / 250 pages.
- `/api/health` liveness probe; one-click Vercel deploy (`vercel.json`).
- `bun run parity` harness (worker, geometry, full) and `bun run check` vendor gate.

### Changed

- Uniform A4 output pages with thin black frame; smaller PDFs via quality/scale defaults.
- README rewrite; upstream `pdf.worker.js` (never rebundled).
- `vercel.json`: dropped `functions` block (conflicts with `builds`); Hobby defaults apply.

### Fixed

- EXIF orientation on phone photos (`Pillow` `exif_transpose` with `imdecode` fallback).
- `vercel.json` build/route conflict.

## [0.1.0] — 2026-09-14

### Added

- Initial web product: Flask routes, image scan API, server PDF scan with SSE progress, web UI.
- Tier-1 scan pipeline integration (`auto_scan.py`) and reference-quality gate.

[Unreleased]: https://github.com/minhazexo/cam-clone/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/minhazexo/cam-clone/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/minhazexo/cam-clone/releases/tag/v0.1.0
