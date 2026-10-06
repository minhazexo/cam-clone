# Testing

Four layers, in increasing cost. Run everything with one command:

```bash
bun run test        # check + parity + JS tests + Python tests
```

| Command | Layer | What it proves |
|---|---|---|
| `bun run check` | asset gate | every vendored/worker artifact the pages load exists |
| `bun run parity` | Python↔JS parity | the browser scanner still matches the Python pipeline |
| `bun run test:js` | frontend units | helpers behave, constants/profiles are consistent, import graphs + asset paths resolve |
| `bun run test:python` | backend units + integration | config/storage/jobs/scanner/PDF units, and every API flow end-to-end |

Individual lanes:

```bash
node tests/parity/parity_worker.js      # photometry stage
node tests/parity/parity_geometry.js    # geometry + cleanups
node tests/parity/parity_full.js        # full pipeline
bun test tests/js                       # frontend
python3 -m unittest tests.unit -v        # backend units only
python3 -m unittest tests.integration -v # API flows only
```

`python3` may be `python` on your platform; CI uses `python`.

## 1. Asset gate (`bun run check`)

`scripts/check.ts` asserts that the exact paths referenced by the templates,
`static/js/core/constants.js`, and `importScripts` exist:
`static/vendor/{runtime.js,pdf.worker.js,opencv.js}` and
`static/js/workers/{scan-worker.js,scan-worker-v2.js,scan-geometry.js}`,
plus both page entrypoints. `bun run build` regenerates the vendored files.

## 2. Parity suite (`bun run parity`)

The regression protection for the scanner algorithm. The browser port is
compared byte-for-byte (mean absolute difference, MAD) against fixtures that the
*Python* pipeline produced:

| Harness | Fixtures | Gates |
|---|---|---|
| `parity_worker.js` | `in_*.rgb` → `exp_*.rgb` | MAD ≤ 3.0, sharpness within ±10 %, dims equal |
| `parity_geometry.js` | `st_*.rgb`, `stages_*.json` | contour null-ness (±2 px), dims exact, MAD ≤ 3.0 (≤ 1.0 for non-rotating stages), tilt ±0.15° |
| `parity_full.js` | `in_*.rgb` → `full_*.rgb` | dims exact, MAD ≤ 3.0, tilt and sharpness gates |

Reading a failure:

* **MAD ≤ 1** — normal resampling/tie-break noise between NumPy and JS.
* **MAD 1–3** — acceptable but suspicious on non-rotating stages; check if you
  touched rounding (`Math.floor` vs `Math.round`, banker's rounding).
* **MAD > 3 or wrong dims** — a real behavioural change. Find it; do not raise
  the gate.

Fixtures live in `tests/fixtures/` (committed). Regenerate **only** for an
intentional pipeline change:

```bash
python scripts/gen_fixtures.py    # in/exp/full rgb + <name>.json
python scripts/dump_stages.py     # per-stage st_*.rgb + stages_*.json
python scripts/dump_rgb.py        # in_*.rgb from the committed PNGs
```

Then explain in the PR and `CHANGELOG.md` what moved and why (expected MAD,
sharpness delta). Committed fixtures were produced with the reference assets
absent, which is also how CI runs.

## 3. Frontend tests (`bun run test:js`)

* `tests/js/helpers.test.js` — `safeFilename`, `formatBytes`, error messages,
  selection signatures, endpoint builders, PDF profile invariants, local limits.
* `tests/js/assets.test.js` — every `/static/...` path mentioned in
  `core/constants.js` and the templates exists on disk; every relative ES-module
  import resolves; the worker's `importScripts` target exists.

DOM-heavy behaviour (panels, modal, drag & drop) is exercised through the
integration tests (rendered HTML contract) and manual checks on both pages,
since there is no headless-browser dependency in this repository by design.

## 4. Python tests (`bun run test:python`)

`tests/unit/`
* `test_config_and_errors.py` — settings defaults/env parsing, error status codes
* `test_storage.py` — save/read/exists/delete/path, name sanitisation, traversal
* `test_jobs.py` — event payloads, store transitions, TTL cleanup, SSE frames
* `test_scanner.py` — geometry/photometry/image-io behaviour (not exact pixels)
* `test_pdf_layer.py` — page border, A4 assembly, orientation, legacy page size

`tests/integration/test_web_flows.py` — one test class per flow, all through the
Flask test client with an isolated temp storage root and a low PDF DPI:

* health + both pages (asserting the DOM ids the frontend needs)
* `POST /api/scan`: descriptors, dedupe, skipped files, PDF rejection, download
* `POST /api/scan-pdf`: result name, download, temp cleanup, validation
* `POST /api/scan-pdf-start` + SSE: event order, page counts, cleanup,
  unknown job 404
* error handling: JSON for `/api/*`, HTML for pages, 413 for oversized bodies

Add a test for every behaviour change: unit tests for pure functions,
integration tests for endpoint/flow changes.

## Manual verification checklist

Automated tests do not exercise the browser. Before shipping a frontend change,
check on `/` and `/scan-pdf`:

1. page renders styled (no missing `style.css`), console free of errors;
2. drag & drop and the pickers work; the page-limit modal opens and cancels;
3. `/scan-pdf` shows "Scan engine ready (v2-full)" before enabling the button;
4. image scan → result cards with previews and working downloads;
5. server PDF scan → live step log/progress → PDF download;
6. on-device PDF scan → A4 pages with frames → "Download All" works;
7. "Scan more" returns to the upload view and revokes blob URLs (no leak);
8. mobile viewport: layout is usable and the render cap kicks in.

## Quality gate (local only)

`python scripts/quality_gate.py` compares a pipeline run against the local
reference assets (`Work Images/`, git-ignored) with reference-anchored
statistics (photometry, PSNR/SSIM/MAD, tilt, margins). It exits non-zero on
regression and needs those assets, so it is a workstation tool, not a CI gate.
The historical path `RScan/Python/scan/quality_gate.py` still works.

## CI

`.github/workflows/ci.yml` runs four jobs: frontend asset check + parity,
JS tests, Python unit + integration tests, and a Python compile/import smoke
test. Keep it fast — the whole suite is under a couple of minutes.
