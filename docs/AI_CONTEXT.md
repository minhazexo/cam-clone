# AI context (condensed)

Use this when you need to load the project into a fresh context quickly. It is
a compression of `AGENTS.md` + `docs/ARCHITECTURE.md`, not a replacement —
read those before making non-trivial changes.

## What this is

RScan — a CamScanner-style web document scanner. Flask + OpenCV + NumPy +
PyMuPDF backend, vanilla-JS frontend, OpenCV.js WASM for the on-device path.
GPL-3.0. No database, no secrets, no external services.

## Repository shape (one screen)

```
app.py                     local entrypoint (thin)
api/index.py               Vercel entrypoint (thin, only sys.path user)
rscan/config/settings.py   ALL settings + limits
rscan/web/                 Flask factory, context, routes (thin handlers)
rscan/services/            use-cases: image_scan, pdf_scan, scan_progress
rscan/jobs/                JobStore, worker thread, event vocabulary
rscan/storage/             Storage protocol + LocalTempStorage
rscan/scanner/             the image pipeline (constants, geometry, photometry,
                           preprocessing, postprocessing, reference, image_io,
                           pipeline)
rscan/pdf/                 renderer (pages), assembler (PDF out)
static/js/core|api|ui      frontend infrastructure
static/js/features         image-scan + pdf-scan flows
static/js/workers          OpenCV.js workers, geometry port, engine loader
templates/layouts|partials Jinja layout + shared UI shell
tests/unit|integration|js|parity|fixtures
scripts/                   build.ts, check.ts, fixture generators, quality gate
RScan/Python/scan/         legacy compat shims (documented in AGENTS.md §16)
```

## The three flows

1. images: `POST /api/scan` → image_scan_service → scanner.pipeline → JPEG.
2. server PDF: `POST /api/scan-pdf-start` → job thread → renderer → pipeline →
   assembler → SSE `loading/detected/scanning/page_done/assembling/done`.
3. on-device PDF: `/scan-pdf` → pdf.js → worker (OpenCV.js) → pdf-lib → blob.

## The one thing that is easy to get wrong

The scanner exists twice: Python (`rscan/scanner/`) and JavaScript
(`static/js/workers/`). They must stay numerically identical. Constants,
operation order, rounding (Python `int()` truncates, `round()` is banker's) and
channel conventions are all load-bearing. `bun run parity` proves it with
committed fixtures; never regenerate fixtures to silence a failure.

## Where to look first for…

| Task | File |
|---|---|
| change a scan limit / DPI / quality | `rscan/config/settings.py` (+ `static/js/core/constants.js`) |
| change document detection | `rscan/scanner/geometry.py` (+ `scan-geometry.js`) |
| change enhancement look | `rscan/scanner/photometry.py` (+ `scan-worker-v2.js`) |
| change trims/framing | `rscan/scanner/postprocessing.py` (+ `scan-geometry.js`) |
| change pipeline order | `rscan/scanner/pipeline.py` (+ `processPage`) |
| add an API endpoint | new module in `rscan/web/routes/` + blueprint registration |
| change PDF output layout | `rscan/pdf/assembler.py` (+ `pdf-export.js`) |
| change progress UI | `static/js/ui/progress.js`, `features/pdf-scan/pdf-progress.js` |
| change the page shell | `templates/layouts/base.html`, `templates/partials/*` |
| add a test | `tests/unit/`, `tests/integration/`, `tests/js/` |

## Commands

```bash
python app.py             # run locally  (python3 if that is your interpreter)
bun run test              # check + parity + JS + Python tests
bun run parity            # scanner parity only
bun run build             # rebuild vendor/runtime.js + pdf.worker.js
```

## Invariants (short list)

* routes stay thin; scanner/pdf know nothing about Flask;
* config has one source per side (Python settings, JS constants);
* worker + vendor paths are a contract (constants, templates, importScripts, tests);
* template ids are a contract with the frontend modules;
* error bodies are `{"error": "…"}` and never leak tracebacks;
* no scan logic in `api/index.py` or `app.py`.
