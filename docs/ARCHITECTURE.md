# Architecture

RScan is a single Python package (`rscan`) behind a thin Flask shell, plus a
vanilla-JS frontend that can also run the whole scan pipeline in the browser.
This document explains the boundaries, the flows, and why they are drawn this
way. For editing guidance see `AGENTS.md`; for endpoint details see `API.md`.

## 1. System overview

```
┌──────────────────────────── Browser ────────────────────────────┐
│  /                      /scan-pdf                               │
│  ├─ static/js/app.js     ├─ static/js/scanpdf.js                │
│  ├─ features/image-scan  ├─ features/pdf-scan/*                 │
│  └─ ui/*, core/*, api/*  └─ workers/engine-loader.js            │
│                                  │                              │
│                          workers/scan-worker-v2.js (OpenCV.js)   │
└───────────────┬──────────────────────────────────┬──────────────┘
                │ fetch / SSE                      │ (no network)
┌───────────────▼──────────────────────────────────┴──────────────┐
│ Flask (rscan.web)                                                │
│  routes: health · pages · scan · pdf · images                    │
│  app_factory: settings, storage, job store, error handlers        │
├──────────────────────────────────────────────────────────────────┤
│ Services (rscan.services)                                        │
│  image_scan_service · pdf_scan_service · scan_progress_service     │
├──────────────┬───────────────┬───────────────┬───────────────────┤
│ rscan.scanner│ rscan.pdf     │ rscan.jobs    │ rscan.storage      │
│ pipeline     │ renderer      │ job_store     │ LocalTempStorage   │
│ geometry     │ assembler     │ job_worker    │ (upload dir)       │
│ photometry   │ pdf_service   │ events        │                    │
└──────────────┴───────────────┴───────────────┴───────────────────┘
```

## 2. Components and responsibilities

| Component | Owns | Must not |
|---|---|---|
| `rscan.web` | HTTP shape: routes, validation, status codes, error translation | contain scan logic, threads, or file handling |
| `rscan.services` | use-cases that combine domain + storage + jobs | import Flask |
| `rscan.scanner` | the image pipeline (pure OpenCV/NumPy) | know about HTTP, files, or jobs |
| `rscan.pdf` | PDF page rendering and PDF assembly (PyMuPDF) | know about jobs or HTTP |
| `rscan.jobs` | job state, worker thread, progress vocabulary | know about Flask request objects |
| `rscan.storage` | artifact persistence | contain scan logic |
| `rscan.config` | every setting and limit | be bypassed by ad-hoc env reads |
| `static/js/core` | constants, logging, errors, DOM helpers, session state | import feature modules |
| `static/js/api` | HTTP clients + SSE subscription | touch the DOM |
| `static/js/ui` | panels, modal, results rendering, upload zone | know about scan maths |
| `static/js/features` | image/PDF flows | duplicate constants or UI helpers |
| `static/js/workers` | OpenCV.js workers + geometry port + engine loader | use ES module imports (classic workers) |

## 3. Request lifecycle (server PDF job)

```
1  POST /api/scan-pdf-start        routes/pdf.py: validate → storage.save(input) →
                                   job_store.create() → start_pdf_scan_job()
2  background thread               services/pdf_scan_service.scan_pdf_streaming()
                                     · rendering   (pdf.renderer)
                                     · scanning    (scanner.pipeline, ThreadPool)
                                     · assembling  (pdf.assembler)
                                   each step → on_event(events.*) → job.queue
3  GET  /api/scan-pdf-progress/<id> services/scan_progress_service.stream_job()
                                   queue → SSE frames (+ keepalive comments)
4  GET  /api/pdf/<name>            routes/pdf.py → storage.path → send_file
5  worker finally                  delete temp input, push `_eof`, log with job id
```

Failures inside the job never surface as HTTP errors: they become an `error`
event on the stream (and a logged traceback).

## 4. Browser/server boundaries

| Concern | Browser | Server |
|---|---|---|
| Image scan | shows results, downloads | decodes, scans, encodes |
| PDF (server path) | uploads, renders SSE progress | renders, scans, assembles |
| PDF (on-device path) | everything: render, scan, assemble | nothing (no request) |
| Limits | 250 MB / 250 pages local caps | 50 MB request cap, job TTL |
| Secrets | none | none (no API keys anywhere) |

The public API is deliberately small: nine endpoints, JSON in/out, SSE for
progress. See `API.md`.

## 5. Data flow (image scan)

```
multipart upload → bytes
  → image_io.decode_image_bytes (Pillow EXIF → RGB → BGR; cv.imdecode fallback)
  → pipeline.scan_photo_to_reference  (BGR → BGR, geometry + photometry)
  → image_io.encode_jpeg(quality=95)
  → storage.save("<file_id>.jpg")        → {"pages":[{name,id,width,height}]}
```

## 6. Dependency direction

```
web → services → {scanner, pdf, jobs} → storage
                         ↘ config / errors / logging_config ↙
```

* No cycles: `web/routes/*` import `web/context.py` (not `app_factory.py`).
* `scanner` has no dependency on `pdf` (PDF layer calls the scanner, not the
  other way around).
* Tests import the same layers the app does; nothing special-cased for tests.

The complete rule list ("routes carry no business logic", "no cycles", "no
dead code", "no hidden global state", …) is maintained as **project law** in
`AGENTS.md` → §21 *Architectural rules*, next to the invariants in §14. Add a
rule there, not here.

## 7. Storage flow

```
LocalTempStorage(root=settings.upload_dir)
  save(name, bytes)   atomic write (tmp file + os.replace)
  path(name)          raises ResultNotFoundError when missing
  write_path(name)    for writers that need a filename (PyMuPDF)
  delete(name)        best-effort
```

Artifacts: `in_<hex8>.pdf` (transient input), `scanned_<hex8>.pdf` (result),
`<hex12>.jpg` (scanned image). Names are sanitised (`sanitize_name`), so a
crafted URL cannot escape the root.

## 8. Job lifecycle

```
created ──► running ──► done | error ──► (TTL) deleted
   │            │
   │            └─ events: loading, detected, scanning, page_done, assembling
   └─ SSE consumers attach/detach freely; detaching does not cancel the job
```

* Jobs live in memory per process (`JobStore`, TTL 600 s, cleanup on start).
* A job's queue is written under a lock; the SSE generator reads the queue
  object once and blocks on it.
* Streams end on `done`/`error`; `_eof` is an internal close sentinel.

## 9. Deployment architecture

```
Local:  python app.py  → Flask dev server (threaded, needed for SSE)
Vercel: vercel.json → api/index.py → create_app()  (one WSGI app, many instances)
```

Absolute template/static paths keep both working. Serverless differences
(ephemeral `/tmp`, per-instance job store, ~4.5 MB body cap) are documented in
`DEPLOYMENT.md`; the on-device path is the answer to all three.

## 10. Why these choices (short version)

* **Flask + vanilla JS kept** — the app is a handful of endpoints and two pages;
  a framework migration would add build complexity without removing any logic.
* **Python package instead of `sys.path` hacks** — imports are explicit and
  testable; the only path bootstrap left is the Vercel entrypoint.
* **One pipeline, two implementations (Python + JS)** — the on-device path must
  run without a server, and the parity suite keeps both honest.
* **In-memory jobs + SSE** — matches the single-process deployment model and
  avoids adding a broker for a feature that already degrades gracefully.

Details: `docs/decisions/`.
