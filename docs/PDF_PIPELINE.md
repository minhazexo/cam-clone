# PDF pipelines

There are three PDF-related flows. They share one idea — *render pages, scan
each page, assemble uniform pages* — implemented twice (Python and browser)
with matching defaults.

| Flow | Entry point | Where it runs | Progress |
|---|---|---|---|
| Server scan (sync) | `POST /api/scan-pdf` | server | none (single response) |
| Server scan (job) | `POST /api/scan-pdf-start` + SSE | server | per page over SSE |
| On-device scan | `/scan-pdf` page | browser | per page in the panel |

Both server flows call the same code
(`rscan/services/pdf_scan_service.py`), so behaviour cannot drift between them.

## Server pipeline

```
PDF bytes (upload)
  → storage.save("in_<hex8>.pdf")
  → rscan.pdf.renderer.iter_pdf_pages_as_bgr(dpi=200)      PyMuPDF get_pixmap
       · CMYK → RGB (255 − v), grayscale → BGR
  → rscan.scanner.pipeline.scan_photo_to_reference(page, output_scale=1.0)
       · parallel across CPU cores, bounded by settings.pdf_max_workers (≤ 8)
  → rscan.pdf.assembler.save_bgr_pages_as_pdf(...)
       · per page: optional black frame → JPEG q78 → embed
       · page size A4, orientation matched to the image, margin 0 (full-bleed)
       · PyMuPDF save(garbage=4, deflate=True)
  → storage.write_path("scanned_<hex8>.pdf")
  → client downloads via GET /api/pdf/<name>
```

Why these defaults:

* **200 DPI** keeps note-page text crisp while staying far below 300 DPI in
  pixels and bytes per page.
* **`output_scale=1.0`** because the render is already the target resolution;
  the 2.0× Lanczos path is for the reference-sized *image* scans.
* **A4 + margin 0 + orientation match** gives uniform pages with no white
  bands on two sides. Reference outputs keep a thin black frame
  (`draw_page_border`, ~0.3 % of the short side).
* **Parallel page scanning** is safe because `scan_photo_to_reference` is pure:
  no shared state, no globals beyond the read-only reference cache.

Job-specific behaviour (`rscan/jobs/job_worker.py`):

```
push loading → render all pages → push detected(total)
             → parallel scan, push scanning/page_done (monotonic counter)
             → push assembling → write PDF
             → push done(pdf, elapsed)
finally: delete input, push _eof
```

Failures push `error(message)` and still push `_eof`, so the SSE stream always
closes. Every log line in the worker carries the `job_id`.

## On-device pipeline

```
File (PDF)
  → pdf-engine.js      wait for window.pdfjsLib / window.PDFLib (runtime.js)
  → pdf-renderer.js    page.getViewport({scale}) → canvas   (whole chunk, concurrent)
         scale = min(200/72, capWidth/pageWidth)      cap 2500 (desktop) / 1800 (phone)
  → pdf-processing.js  canvas → worker protocol → enhanced canvas   (one worker/page)
  → pdf-export.js      optional frame → JPEG → pdf-lib embedJpg      (document order)
         pageMode "a4"     → uniform A4 page, aspect-fit, centred
         pageMode "source" → the PDF's own page size (legacy fallback profile)
  → pdf-lib save()     → Blob → object URL (state.js owns revocation)
```

### Parallel scanning (worker pool)

Pages are processed in **chunks of N**, where N is the worker-pool size
(`core/constants.js: scanPoolSize`, chunks built by
`pdf-processing.js: planPageChunks`):

1. render every page of the chunk concurrently (pdf.js rasterises off the
   main thread);
2. scan the chunk with **one OpenCV.js worker per page** — this is the
   expensive stage, ~90 % of the per-page cost, so N workers means N pages
   advancing at a time;
3. encode and append those pages strictly in document order, releasing each
   canvas as soon as it is embedded (so only one chunk of full-size canvases
   is ever alive).

`N = min(pages, 4, hardwareConcurrency - 1)`, capped at 2 on small screens,
and always 1 for a single page and for the `fallback` profile. Extra workers
are warmed lazily (`engine-loader.js: acquirePool`) and kept alive for the
next scan, so the ~10 MB WASM compile is paid once per worker per page load.
If a spare worker cannot warm up, the scan simply runs with a smaller pool.

Profiles (`static/js/core/constants.js: PDF_PROFILES`) keep the two local paths
honest:

| | `full` (`/scan-pdf`) | `fallback` (home page last resort) |
|---|---|---|
| Render | 200 DPI, width-capped | 2× capped at 1500 px wide |
| Worker | warm engine **pool** (v2, else v1) | v1 light worker (single) |
| Output pages | uniform A4 + frame | the PDF's own page size |
| JPEG quality | 0.80 | 0.94 |

Nothing is uploaded in either case; the only limits are the local caps
(250 MB / 250 pages).

## Assembly parity with the server

The browser writes PDFs with pdf-lib, the server with PyMuPDF, so the *bytes*
differ, but the *layout* matches:

* same page size (A4 portrait/landscape by image orientation),
* same aspect-fit and centring maths,
* same frame ratio (0.3 % of the short side, inset one stroke),
* same JPEG quality default on the `/scan-pdf` path.

If you change one side, change the other and re-check a rendered page.

## Failure modes

| Symptom | Cause | Handling |
|---|---|---|
| `500 {"error": …}` on `/api/scan-pdf` | not a real PDF, corrupt page | sanitised processor message; traceback logged |
| `error` event mid-stream | one page failed to scan | job stops, temp input removed, stream closes |
| `403`-style body caps | Vercel ~4.5 MB limit | use the on-device path |
| `Job not found` | TTL expiry or another instance | re-start the job |
| `PDF load timed out after 60s` | pdf.js worker blocked | check `/static/vendor/pdf.worker.js` |
| `Scan engine is still warming up` | OpenCV.js still parsing | wait for the status line to say "ready" |
