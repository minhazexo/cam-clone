# RScan — Smart Document Scanner

A CamScanner-style document scanner for the web. Upload phone photos or PDFs and get clean, flat, high-contrast scans with uniform A4 pages — via the server API or **fully on-device in the browser** (no size limits, no uploads).

## Features

- **Two scan paths:** server API (Flask + OpenCV + PyMuPDF) and on-device (`/scan-pdf`: pdf.js + OpenCV-WASM worker + pdf-lib) with near bit-exact parity (MAD ≤ 0.05 vs the Python pipeline).
- **Reference-quality output:** perspective/contour warp, ruling-based dewarp and keystone correction, auto deskew (including colored-ruling detection), margin trims, illumination flattening, white/black-point stretch with color-preserving ink, light unsharp pass.
- **Clean note pages:** every output page is uniform A4 (portrait or landscape matched), full-bleed, with a thin black frame — no giant pixel-sized pages, no white borders.
- **Live PDF progress:** server PDF jobs stream per-page progress over SSE; the browser path shows the same step log + progress bar locally.
- **Page-limit picker:** 10 / 20 / 30 / 40 / 50 / All Pages modal on both scan pages (local cap: 250 MB, 250 pages).
- **Deploy-ready:** one-click Vercel deploy (`vercel.json` tuned: 60 s / 1024 MB function), plus a `/api/health` probe.

## Quickstart (local)

```bash
pip install -r requirements.txt   # headless OpenCV — no libGL needed
bun run build                     # vendor runtime.js + pdf.worker.js (opencv.js is pre-vendored)
python app.py                     # → http://localhost:5000
```

Open `/` for images + server PDF scans, or `/scan-pdf` for the unlimited on-device flow.

## Deploy (Vercel)

1. Import the repo in Vercel (framework: Other, root: repo root). No build command needed.
2. Deploy, then check `https://<project>.vercel.app/api/health` → `{"status":"ok"}`.
3. Open `/scan-pdf` and wait for “Scan engine ready (v2-full)”.

> Honest limits on serverless: ~4.5 MB request bodies, 60 s per request, ephemeral disk. Image scans and small PDFs work; 100-page server scans belong on `python app.py` locally. The `/scan-pdf` page is unaffected — it never touches the server. Full matrix: `docs/08-VERCEL_DEPLOYMENT.md`.

## Usage

| Flow | Where | Notes |
|---|---|---|
| Scan images | `/` → Scan Images | Multi-file, deduped, JPEG q95 back |
| Scan PDF (server, SSE) | `/` → Scan PDF | Page-limit modal, live `page_done` events |
| Scan PDF (on-device) | `/scan-pdf` | Any size; engine WASM downloads once (~10 MB, cached) |
| CLI single/batch | `python RScan/Python/scan/scan_pdf.py in.pdf out.pdf [--dpi 200] [--jpeg-quality 78] [--page-size A4\|Letter\|keep] [--margin 0] [--no-border] [--output-scale 1.0]` | Same defaults as the server |
| Quality gate | `python RScan/Python/scan/quality_gate.py` | Reference-anchored regression checks (needs reference assets) |

### API

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web UI |
| `/scan-pdf` | GET | On-device scan page |
| `/api/health` | GET | `{status, service}` liveness probe |
| `/api/scan` | POST | `files[]` images → `{pages: [{name, id, width, height}]}` (PDFs rejected: use the PDF flow) |
| `/api/scan-pdf` | POST | Legacy single-shot PDF → `{pdf}` |
| `/api/scan-pdf-start` | POST | Starts background job → `{job_id}` |
| `/api/scan-pdf-progress/<job_id>` | GET (SSE) | `loading → detected → scanning → page_done → assembling → done` |
| `/api/image/<id>` · `/api/pdf/<name>` | GET | Serve results (best-effort on serverless) |

## Project structure

```
app.py                  # Flask app: routes, SSE job store, PDF worker threads
api/index.py            # Vercel entrypoint (re-exports app)
RScan/Python/scan/
  auto_scan.py          # core pipeline: geometry → photometry → reframe
  scan.py               # legacy GCMODE/RMODE/SMODE + functional API
  scan_pdf.py           # PDF/image/dir → scanned PDF (DPI, quality, A4, border)
  quality_gate.py       # offline regression gate vs reference
templates/              # index.html (main UI), scan_pdf.html (on-device page)
static/js/              # app.js, scanpdf.js (page flow), scan-worker-v2.js (pipeline),
                        # scan-geometry.js (geometry port), opencv-loader.js, scan-worker.js (fallback)
static/vendor/          # runtime.js, pdf.worker.js (built) + opencv.js 4.8.0 (vendored)
scripts/                # build.ts, check.ts, gen_fixtures.py, dump_stages.py
tests/                  # parity harnesses (parity_worker/geometry/full) + fixtures
docs/                   # deep-dive docs (local only, git-ignored)
```

## Configuration

`.env` (see `.env.example`): `PORT` (default 5000), `RSCAN_DEBUG=1` for debug logs. No API keys required.

## Development & verification

```bash
bun run scripts/check.ts        # vendor artifacts present
bun run parity                  # all three parity harnesses (worker, geometry, full)
python scripts/gen_fixtures.py  # regenerate synthetic fixtures
python scripts/dump_stages.py   # per-stage reference bytes for new fixtures
```

## Tech stack

Flask 3 · OpenCV (headless) · NumPy · PyMuPDF · pdf.js 3.11 · pdf-lib · opencv.js 4.8 (WASM) · Bun build.

## License

GPL-3.0 — see [LICENSE](LICENSE). Origin: RScan by Sourabh Khemka; web product, Tier-1 pipeline and on-device port developed on top.
