# AGENTS.md — RScan for AI coding agents

This file is the fastest way to become productive in this repository. Read it
top to bottom before editing anything; it takes ~5 minutes and prevents the
most expensive mistakes (breaking the Python↔JavaScript parity contract, or
moving a worker path that the browser and the parity harnesses both load).

Companion documents:

| Document | Read it when you need |
|---|---|
| `docs/ARCHITECTURE.md` | system overview, request lifecycle, layering rules |
| `docs/API.md` | every endpoint, request/response shape, error codes |
| `docs/SCAN_PIPELINE.md` | the image pipeline stages + worker protocol |
| `docs/PDF_PIPELINE.md` | server and on-device PDF flows |
| `docs/FRONTEND_ARCHITECTURE.md` | frontend modules, page lifecycle, state |
| `docs/TESTING.md` | exact verification commands |
| `docs/DEPLOYMENT.md` | local run, Vercel, serverless limits |
| `docs/AI_CONTEXT.md` | condensed context for a fresh agent session |
| `docs/decisions/` | why the architecture looks like this (ADRs) |

---

## 1. Project purpose

RScan is a web document scanner in the style of CamScanner. It turns phone
photos and PDFs into clean, flat, high-contrast A4 scans.

Three user-facing flows:

1. **Image scan** (`/`): upload photos → the server runs the OpenCV pipeline →
   scanned JPEGs are returned for download.
2. **Server PDF scan** (`/`, drop a PDF): the PDF becomes a background job →
   per-page progress streams over SSE → a scanned PDF is returned.
3. **On-device PDF scan** (`/scan-pdf`): pdf.js renders pages, an OpenCV.js web
   worker enhances them, pdf-lib assembles the PDF. Nothing is uploaded, so no
   server size/time limits apply.

## 2. Architecture overview

```
Browser ──/api/scan────────────► rscan.web.routes.scan
        ──/api/scan-pdf*───────► rscan.web.routes.pdf ─► rscan.services.pdf_scan_service
        ──/api/health──────────► rscan.web.routes.health        │
                                                                ├─► rscan.pdf.renderer   (PyMuPDF → BGR pages)
                                                                ├─► rscan.scanner.pipeline (OpenCV pipeline)
                                                                ├─► rscan.pdf.assembler  (BGR pages → PDF)
                                                                └─► rscan.jobs.*         (state + worker + events)
                                                                    ▲
Browser ──/api/scan-pdf-progress/<id> (SSE) ────────────────────────┘
        ──/api/image/<id>, /api/pdf/<name> ─► rscan.storage

Browser only: static/js/features/pdf-scan/* ─► static/js/workers/scan-worker-v2.js (OpenCV.js)
```

Dependency direction (never reverse it):

```
rscan.web  →  rscan.services  →  { rscan.scanner, rscan.pdf, rscan.jobs }  →  rscan.storage
                                          ↓
                                   rscan.config, rscan.errors, rscan.logging_config
```

## 3. Important directories

| Path | What lives there | Notes |
|---|---|---|
| `app.py` | local entrypoint (`create_app()` + dev server) | thin on purpose |
| `api/index.py` | Vercel entrypoint | only file allowed to touch `sys.path` |
| `rscan/config/` | all settings/env vars | single source of truth |
| `rscan/web/` | Flask factory, routes, response helpers | no business logic |
| `rscan/services/` | use-cases (image, PDF, SSE translation) | no Flask imports |
| `rscan/jobs/` | job state, worker thread, event vocabulary | |
| `rscan/storage/` | artifact storage abstraction | |
| `rscan/scanner/` | **the scanner algorithm** (geometry/photometry/post) | parity-sensitive |
| `rscan/pdf/` | PDF rendering + assembly | |
| `static/js/core/` | constants, logger, errors, DOM helpers, session state | |
| `static/js/api/` | one module per API surface | |
| `static/js/ui/` | panel/modal/results/upload-zone controllers | |
| `static/js/features/` | image-scan and pdf-scan flows | |
| `static/js/workers/` | OpenCV.js workers + geometry port + engine loader | path contract |
| `templates/` | Jinja layout + partials + pages | ids are a contract |
| `tests/` | `unit/`, `integration/`, `js/`, `parity/`, `fixtures/` | |
| `scripts/` | build, parity fixture generators, quality gate | |
| `RScan/Python/scan/` | **legacy compatibility shims** | see §16 |

## 4. Backend flow (image scan)

`POST /api/scan` → `rscan/web/routes/scan.py`
→ `rscan/services/image_scan_service.py` (dedupe, extension policy, decode)
→ `rscan/scanner/image_io.py` (EXIF-aware decode)
→ `rscan/scanner/pipeline.py:scan_photo_to_reference`
→ `rscan/storage` (`<file_id>.jpg`)
→ JSON `{"pages": [{name, id, width, height} | {name, error}]}`

## 5. Server PDF flow

`POST /api/scan-pdf-start` → store the upload → `rscan/jobs/job_worker.start_pdf_scan_job`
→ `rscan/services/pdf_scan_service.scan_pdf_streaming`:

```
loading → detected(total) → scanning/page_done (parallel, monotonic counter)
        → assembling → done(pdf, elapsed)
```

Events are pushed into the job's queue (`rscan/jobs/job_store.py`) and
translated to SSE frames by `rscan/services/scan_progress_service.py`, which is
served by `GET /api/scan-pdf-progress/<job_id>`. `POST /api/scan-pdf` is the
synchronous variant (no progress).

## 6. On-device PDF flow

`static/js/features/pdf-scan/`:

```
pdf-engine.js (pdf.js + pdf-lib ready)
  → pdf-renderer.js  (chunk of pages → canvas at profile DPI)
  → pdf-processing.js(canvas → worker pool → enhanced canvas; 1 worker/page)
  → pdf-export.js    (embed JPEG → A4 page, optional frame, in page order)
  → pdf-lib save()   → blob URL → /api/pdf-* never involved
```

Pages are processed in chunks of `scanPoolSize(...)` (pool size) so N pages
scan at once; the append step stays strictly ordered. Do not send two requests
to one worker — each worker holds one in-flight message (`core/constants.js`,
`planPageChunks`, `engine-loader.acquirePool`).

## 7. Scanner pipeline (server)

`rscan/scanner/pipeline.py:scan_photo_to_reference` orchestrates, in order:

```
load → (template align | contour warp | ruling dewarp | deskew)
     → pre-enhance trims (dark edges, white fill, smeared top, margins)
     → photometry (high-pass flatten → white point → black point ×2)
     → reframe → binding removal → residual deskew → top trim
     → second reframe → corner/border whitening
     → unsharp → final size fit
```

Details and per-stage rationale: `docs/SCAN_PIPELINE.md`.

## 8. Python ↔ JavaScript parity relationship

The same algorithm exists twice:

| Python | JavaScript |
|---|---|
| `rscan/scanner/pipeline.py` | `static/js/workers/scan-worker-v2.js` (`processPage`) |
| `rscan/scanner/geometry.py` | `static/js/workers/scan-geometry.js` |
| `rscan/scanner/photometry.py` | `static/js/workers/scan-worker-v2.js` (`enhanceReferenceLook`) |

Parity is enforced by three Node harnesses in `tests/parity/` that compare the
JS output against committed fixtures produced by the Python pipeline:

* `parity_worker.js` — photometry stage (MAD ≤ 3.0)
* `parity_geometry.js` — geometry stages + cleanups (MAD ≤ 3.0, dims exact)
* `parity_full.js` — full pipeline (dims exact, MAD ≤ 3.0, tilt/sharpness gates)

Fixtures in `tests/fixtures/` are the baseline. **Never regenerate them to make
a failing parity run pass** — that erases the regression signal.

## 9. Worker protocol

```
request   { width, height, pixels: ArrayBuffer }         RGBA, transferred
response  { width, height, pixels: ArrayBuffer, stats }  RGBA, transferred
error     { error: string }
warmup    { ping: true } → { ready: true, engine: "v2-full" }
```

The buffers are transferable (zero-copy) and every `cv.Mat` is deleted inside
the worker. Full description: `docs/SCAN_PIPELINE.md` → "Worker protocol".

## 10. API overview

`GET /` · `GET /scan-pdf` · `GET /api/health` · `POST /api/scan` ·
`POST /api/scan-pdf` · `POST /api/scan-pdf-start` ·
`GET /api/scan-pdf-progress/<job_id>` (SSE) · `GET /api/image/<id>` ·
`GET /api/pdf/<filename>`. All error bodies are `{"error": "…"}`.

Full contract: `docs/API.md`.

## 11. How to run locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
bun install && bun run build        # optional: rebuilds static/vendor artifacts
python app.py                       # → http://localhost:5000
```

`bun run build` is only needed after changing `static/js/runtime.ts` or
upgrading `pdfjs-dist`; the vendored outputs are committed.

## 12. How to run tests

```bash
bun run test        # check + parity + JS unit + Python unit/integration
bun run check       # frontend artifacts exist
bun run parity      # Python↔JS regression harnesses
bun run test:js     # frontend unit + asset-contract tests
bun run test:python # unittest discovery (unit + integration)
```

Exact commands, what each gate proves, and how to add tests:
`docs/TESTING.md`.

## 13. How to deploy

* **Local:** `python app.py` (PORT env var, default 5000).
* **Vercel:** import the repo; `vercel.json` routes everything to
  `api/index.py`. No build command, no API keys.
* Verify after deploy: `GET /api/health` → `{"status": "ok", "service": "rscan"}`.

Serverless caveats (ephemeral `/tmp`, ~4.5 MB body cap, single-instance job
namespace): `docs/DEPLOYMENT.md`.

## 14. Important invariants

1. **Parity.** Any change to a number, operation order, rounding rule, kernel
   size, or channel convention in `rscan/scanner/*` must be mirrored in
   `static/js/workers/*` and pass `bun run parity`.
2. **Route handlers stay thin.** Validate → call a service → return a response.
3. **`rscan/scanner/*` and `rscan/pdf/*` never import Flask or HTTP code.**
4. **Configuration has one source:** `rscan/config/settings.py` (backend) and
   `static/js/core/constants.js` (frontend). Do not restate limits elsewhere.
5. **Worker + vendor paths are a contract:** `/static/js/workers/*.js` and
   `/static/vendor/*` are referenced by `core/constants.js`, the templates,
   `importScripts`, and `tests/parity/*`. Moving them means updating all four.
6. **Template ids are a contract:** `uploadZone`, `fileInput`, `stepLog`,
   `resultsGrid`, `pageLimitBackdrop`, … are looked up by the frontend modules.
7. **Error bodies are always `{"error": "…"}`** and never contain tracebacks.
8. **One source of truth for scan limits:** server 50 MB request cap /
   250 MB local PDF / 250 local pages.
9. **No hidden global mutable state** except the documented reference-measurement
   caches in `rscan/scanner/reference.py` and the per-process job store.

## 15. Things an AI must NOT change casually

* Algorithm constants in `rscan/scanner/constants.py` (white/black point,
  saturation, kernel divisor, reference margins/aspect, output scale).
* The order of pipeline stages in `scan_photo_to_reference` and the
  post-enhance sequencing comments (reframe-then-bind, cleanup-after-reframe).
* `static/js/workers/scan-geometry.js` / `scan-worker-v2.js` math.
* `static/vendor/pdf.worker.js` (copied verbatim; rebundling breaks pdf.js).
* The public API shapes in `docs/API.md`, including HTTP status codes.
* The uploaded-file policy: a PDF in an image batch is a 400, unsupported
  extensions are skipped, undecodable images are skipped.
* `api/index.py`'s path bootstrap (Vercel needs it) and the `template_folder` /
  `static_folder` settings (absolute paths keep serverless working).

## 16. Legacy and compatibility paths

| Component | Status | Why it exists |
|---|---|---|
| `RScan/Python/scan/auto_scan.py` | **compatibility shim** | historical import path; re-exports `rscan.scanner.*` |
| `RScan/Python/scan/scan_pdf.py` | **compatibility shim + CLI** | the documented CLI (`python RScan/Python/scan/scan_pdf.py in.pdf out.pdf`) |
| `RScan/Python/scan/quality_gate.py` | **compatibility shim** | loads `scripts/quality_gate.py` by path |
| `RScan/Python/scan/_compat.py` | compat helper | puts the repo root on `sys.path` for direct execution |
| `RScan/Python/scan/scan.py` | **legacy, still functional** | original GCMODE/RMODE/SMODE modes; not used by the web app |
| `POST /api/scan-pdf` (sync) | **active, secondary** | documented non-SSE alternative to the job flow |
| `static/js/workers/scan-worker.js` | **active fallback** | light enhancer when OpenCV.js cannot load |
| `PDF_PROFILES.fallback` | **active fallback** | home page's last-resort local scan; legacy output preserved |
| `trim_coil_margin` (postprocessing) | **implemented, unused** | parity-ported for future coil work; do not delete |

Do not delete legacy paths without checking callers
(`rg "auto_scan|scan_pdf import|quality_gate"`). If you remove one, update
`CHANGELOG.md` and this table.

## 17. Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Blank page / unstyled preview | template partial not found, or `style.css` path changed | check `templates/layouts/base.html`, `rscan/config/settings.py` |
| `Scan engine is still loading` forever | `/static/vendor/opencv.js` missing, or worker path wrong | `bun run check`, inspect `core/constants.js` asset paths |
| `pdf.js worker … blocked` | `static/vendor/pdf.worker.js` missing/rebundled | `bun run build` (it is copied, never bundled) |
| `Job not found` on progress | job expired (TTL) or another serverless instance served the request | see `docs/DEPLOYMENT.md` |
| Download 404 after a scan | serverless `/tmp` is ephemeral | re-scan; local runs keep artifacts for the session |
| Parity MAD spike | a scanner constant or op order changed on one side only | diff `rscan/scanner` against `static/js/workers` |
| `bun run check` fails | a worker/vendor file was moved without updating the contract | restore the path or update constants + tests + templates |
| Image scan returns `pages: []` | unsupported extension or undecodable bytes | expected; the API skips bad inputs silently |

## 18. Where to modify code for common tasks

See "CHANGE MAP" below.

## 19. Naming conventions

* Python: `snake_case` modules/functions, `PascalCase` classes/dataclasses,
  `SCREAMING_SNAKE_CASE` module constants, one logger per module via
  `logging.getLogger(__name__)`.
* JavaScript: `camelCase` functions/variables, `PascalCase` only for classes
  and typedefs, `SCREAMING_SNAKE_CASE` exported constants, files `kebab-case.js`.
* Modules are named after the single thing they own (`job_store.py`,
  `pdf-renderer.js`), not after the layer (`utils.py`, `helpers.js`).
* Test files: `test_<subject>.py` (Python), `<subject>.test.js` (JS).

## 20. Testing requirements before committing

Minimum for any change:

```bash
bun run check && bun run test:js          # frontend wiring stayed intact
bun run test:python                       # backend units + API flows
bun run parity                            # only if scanner/worker code changed
python -m compileall -q app.py api rscan RScan/Python/scan scripts
```

If you changed the scanner (Python or JS): regenerate nothing, but explain any
intentional fixture change in the PR and in `CHANGELOG.md`. CI runs the same
gates (`.github/workflows/ci.yml`).

## 21. Architectural rules (project law)

These are the rules every change is reviewed against. §14 lists the invariants
that break the product if violated; this list is the structural contract.

1. **Routes do not contain business logic.** A handler validates input, calls a
   service, and returns a response (`rscan/web/routes/*`).
2. **Scanner algorithms do not know about Flask.** Nothing under
   `rscan/scanner/` or `rscan/pdf/` may import web, request, or response code.
3. **Scanner algorithms do not know about HTTP.** No status codes, URLs, or
   request objects — `rscan/errors.py` types are the only escape hatch.
4. **The frontend does not duplicate backend business rules.** Limits, quality
   values and profiles live in `static/js/core/constants.js` and are mirrored
   from `rscan/config/settings.py` deliberately — never re-derived per module.
5. **Worker communication uses documented protocols.** Message shapes are
   specified in `docs/SCAN_PIPELINE.md`; both the browser and the Node parity
   harnesses speak the same protocol.
6. **Configuration comes from one source.** `rscan/config/settings.py` on the
   server, `static/js/core/constants.js` in the browser. No scattered
   `os.environ` / magic numbers.
7. **File storage is isolated.** All read/write/delete goes through
   `rscan/storage/` (`Storage` protocol); services never build paths by hand.
8. **Job state is isolated.** `rscan/jobs/` owns creation, retrieval, TTL and
   cleanup; routes and SSE only read what the store exposes.
9. **The scanner pipeline is deterministic wherever possible.** No randomness,
   no time/locale dependence in `rscan/scanner/*`; reference measurements are
   cached, documented module constants.
10. **Python ↔ JS scanner parity is a protected invariant.** Both sides change
    in the same commit and `bun run parity` must pass.
11. **New scanner behaviour requires regression fixtures/tests.** Extend
    `tests/parity/*` (or add fixtures via `scripts/gen_fixtures.py`) before
    trusting a new branch.
12. **No dead code and no duplicate implementations.** If a second copy of a
    pipeline stage appears, delete one.
13. **No unnecessary abstraction.** A module earns its place by having one job;
    do not add indirection for symmetry.
14. **No circular dependencies.** Layer direction is one way:
    `web → services → { scanner, pdf, jobs, storage } → config/errors`.
15. **No hidden global mutable state** unless the runtime requires it — the only
    accepted cases are the reference measurement caches
    (`rscan/scanner/reference.py`) and the per-process job store.

---

## CHANGE MAP

| If you need to modify… | Start here | Then check |
|---|---|---|
| **image upload / scan endpoint** | `rscan/web/routes/scan.py` → `rscan/services/image_scan_service.py` | `static/js/features/image-scan/`, `static/js/api/scan-api.js` |
| **document detection (corners, warp, dewarp, deskew)** | `rscan/scanner/geometry.py` | `static/js/workers/scan-geometry.js` (**parity**), `docs/SCAN_PIPELINE.md` |
| **image enhancement (flatten, white/black point, saturation)** | `rscan/scanner/photometry.py` | `enhanceReferenceLook` in `static/js/workers/scan-worker-v2.js` (**parity**) |
| **probe/mask helpers** | `rscan/scanner/preprocessing.py` | `probeGray` / `adaptiveInkMask` in `scan-geometry.js` |
| **trims, reframing, binding removal, whitening** | `rscan/scanner/postprocessing.py` | `scan-geometry.js` (**parity**) |
| **pipeline order / step sequencing** | `rscan/scanner/pipeline.py` | `processPage` in `scan-worker-v2.js`, `tests/parity/parity_full.js` |
| **algorithm constants** | `rscan/scanner/constants.py` | JS mirrors + `docs/SCAN_PIPELINE.md` table (**parity**) |
| **browser scanner / worker math** | `static/js/workers/` | `tests/parity/*` (`bun run parity`), `docs/SCAN_PIPELINE.md` |
| **worker warm-up / engine lifecycle** | `static/js/workers/engine-loader.js` | `static/js/features/pdf-scan/pdf-processing.js` |
| **PDF rendering (server)** | `rscan/pdf/renderer.py` | `rscan/services/pdf_scan_service.py` |
| **PDF assembly / A4 pages / border** | `rscan/pdf/assembler.py` | `static/js/features/pdf-scan/pdf-export.js` (browser mirror) |
| **on-device PDF pipeline** | `static/js/features/pdf-scan/` | `static/js/scanpdf.js`, `docs/PDF_PIPELINE.md` |
| **PDF scan endpoints / SSE** | `rscan/web/routes/pdf.py` | `rscan/services/pdf_scan_service.py`, `static/js/api/pdf-api.js` |
| **job state / worker / progress events** | `rscan/jobs/` | `rscan/services/scan_progress_service.py`, `static/js/features/pdf-scan/pdf-progress.js` |
| **artifact storage** | `rscan/storage/` | `rscan/services/*`, `rscan/web/routes/{images,pdf}.py` |
| **settings / limits / env vars** | `rscan/config/settings.py` | `static/js/core/constants.js`, `docs/DEPLOYMENT.md`, `.env.example` |
| **error types / status codes / messages** | `rscan/errors.py` | error handlers in `rscan/web/app_factory.py`, `docs/API.md` |
| **logging behaviour** | `rscan/logging_config.py` | per-module `logging.getLogger(__name__)` |
| **a new API endpoint** | new route module in `rscan/web/routes/` (+ register in `routes/__init__.py`) | service in `rscan/services/`, client in `static/js/api/`, `docs/API.md` |
| **frontend page wiring** | `static/js/app.js` (home) / `static/js/scanpdf.js` (on-device) | `static/js/ui/`, `templates/layouts/base.html` |
| **frontend constants / limits / endpoints** | `static/js/core/constants.js` | `rscan/config/settings.py`, `tests/js/helpers.test.js` |
| **templates / layout / partials** | `templates/layouts/base.html`, `templates/partials/` | the id contract in `docs/FRONTEND_ARCHITECTURE.md` |
| **tests** | `tests/unit/`, `tests/integration/`, `tests/js/` | `docs/TESTING.md` |
| **parity fixtures** | `scripts/gen_fixtures.py`, `scripts/dump_stages.py` | `docs/TESTING.md` (only with an intentional pipeline change) |
| **CI** | `.github/workflows/ci.yml` | `docs/TESTING.md` |
| **deployment** | `vercel.json`, `api/index.py` | `docs/DEPLOYMENT.md` |

If you modify scanner math (Python or JS): run `bun run parity`.
