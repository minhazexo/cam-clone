# Architecture & Data Flow (Deep Dive)

## 1. System diagram (text)
```
Browser (index.html + app.js + scan-worker.js + vendor/runtime.js + pdf.worker.js)
  │  POST /api/scan (images) ──► Flask app.py ──► scan_photo_to_reference() ──► JPG back
  │  POST /api/scan-pdf-start ──► job_id ──► ThreadPoolExecutor scan ──► SSE /api/scan-pdf-progress/<job>
  │  GET  /api/image/<id> , /api/pdf/<name>
  │  Local PDF path (no upload): pdfjs render → pdf-lib assemble, all in browser
  └── Bun-built vendor bridges pdfjs ↔ pdf-lib via window.pdfjsLib / window.PDFLib (runtime.ts)
```

## 2. Backend concurrency (`app.py:43-77,236-300`)
- `_job_store: dict job_id → {queue, pdf_name, error, created_at}` guarded by `_job_store_lock`.
- `_new_job()` → hex uuid. `_push()` JSON-dumps event into queue. `_cleanup_old_jobs()` purges >600s on each start.
- `_scan_pdf_worker(job_id, in_path, original, page_limit)`:
  1. `loading` event → `collect_pages(in_path)` (PyMuPDF render at 300 DPI).
  2. `detected {total}` → slice by page_limit.
  3. `scanning {page:1}` → ThreadPoolExecutor up to 8 workers, each `scan_photo_to_reference(page_img)`, emits `page_done` per future.
  4. `assembling` → `save_bgr_pages_as_pdf()` → `done {pdf, elapsed}`.
  5. Exceptions → `error {message}`. Always: remove input, push `_eof`.
- SSE generator (`app.py:311-325`): 30s `queue.get` timeout → `: keepalive`, yields `data: <payload>`, breaks on `done/error/_eof`. Headers disable nginx buffering.

## 3. Scan core layering
- `scan_photo_to_reference(image)` in `auto_scan.py:976` = **geometry first, photometry second, reframe last**. Never raises on degenerate input (falls back to photometry-only).
- `scan_pdf_to_reference()` in `scan_pdf.py:154` = `collect_pages` → per-page `scan_photo_to_reference` → `save_bgr_pages_as_pdf` (temp JPEGs → PyMuPDF pages sized `w×h` px, `garbage=4, deflate=True`).
- Legacy `scan_image(mode=GCMODE/RMODE/SMODE)` in `scan.py:120` = global-free functional version of old globals-based HPF pipeline; `scan_photo_auto()` tries auto_scan then falls back to GCMODE.
- Quality gate (`quality_gate.py`) is offline regression, not runtime: ECC-aligns output vs reference, checks gray/ink/chroma/PSNR/SSIM/MAD/tilt/margins/edges.

## 4. Frontend layering (`app.js` 31 fns, `index.html`)
- Upload section → Processing (scanner animation + step log + counter + progress) → Results grid + Download All + Scan More + page-limit modal.
- Image flow: `handleFiles` → `POST /api/scan` → `showImageResults` → `GET /api/image/<id>`.
- PDF server flow: `scanPdfWithLiveProgress` → `POST /api/scan-pdf-start` → `EventSource(/api/scan-pdf-progress/<job>)` → `showServerPdfResult`.
- PDF local flow: `scanPdfLocally` (pdfjs render each page → `enhanceCanvas` via `scan-worker.js` → pdf-lib assemble → `showLocalPdfResult`, `clearLocalPdf` revokes URLs).
- Worker `scan-worker.js:10-24`: per-pixel `luminance=0.299r+0.587g+0.114b`, `paper=(lum-35)*1.18+255`, `ink=lum*1.12-18`, blend `amount=(220-lum)/150`.
- `runtime.ts:1-12`: sets `workerSrc=/static/vendor/pdf.worker.js`, exposes `window.pdfjsLib` + `window.PDFLib`.

## 5. Build & vendor reality
- `scripts/build.ts:1-12`: two Bun builds → `static/vendor/runtime.js` (esm) + `pdf.worker.js` (iife), `target:browser, minify:true, sourcemap:external`.
- `scripts/check.ts`: fails if either artifact missing.
- Graph impact: ~90% of 3144 nodes are these two minified files (communities 0-29, 31-44, 46-47, 49, 51-54, 56-60, 62-65, 67-69, 71-75, 78-99, 101-114, 116-118, 120-121). Any "god node" analysis without filtering vendor is misleading — filter `source_file contains vendor` first.

## 6. Failure & security notes (from code)
- Empty image → `ValueError("empty input image")` surfaces as per-file `{error}` in `/api/scan`, or SSE `error`.
- Missing PyMuPDF → `ImportError` early in worker (`app.py:243`).
- No auth, no rate limit; filename traversal blocked by basename + `scanned_` prefix; temp inputs always removed in `finally`.
- `threaded=True` required for SSE + workers (`app.py:362`).
