# API reference

All endpoints are JSON unless stated otherwise. Every error response has the
same shape:

```json
{ "error": "human readable message" }
```

Error messages never contain stack traces or internal paths; technical detail
goes to the server log (`rscan.web.app_factory` handles the mapping).

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | HTML: image scan + server PDF scan |
| `/scan-pdf` | GET | HTML: on-device PDF scan |
| `/api/health` | GET | liveness probe |
| `/api/scan` | POST | scan uploaded images |
| `/api/scan-pdf` | POST | scan a PDF synchronously |
| `/api/scan-pdf-start` | POST | start a background PDF job |
| `/api/scan-pdf-progress/<job_id>` | GET (SSE) | job progress stream |
| `/api/image/<id>` | GET | download a scanned image |
| `/api/pdf/<filename>` | GET | download a scanned PDF |

---

## GET /api/health

Liveness probe used by uptime checks, deploy verification, and the frontend as
a diagnostic when a server scan fails.

* **Request:** none.
* **Response 200:**
  ```json
  { "status": "ok", "service": "rscan" }
  ```
* **Errors:** none (this route cannot fail).
* **Local vs Vercel:** identical.

---

## GET /

Renders the home page: hero, upload zone, processing panel, results panel, and
the page-limit modal (`templates/index.html` → `templates/layouts/base.html`).

* **Response 200:** HTML.
* **Notes:** the page's JS entrypoint is `/static/js/app.js` (ES module).

## GET /scan-pdf

Renders the on-device page (`templates/scan_pdf.html`). Same shell as `/`, plus
an engine-status line. Entrypoint: `/static/js/scanpdf.js`.

---

## POST /api/scan

Scans one or more uploaded images.

* **Request:** `multipart/form-data` with a repeated field `files`.
* **Validation:**
  * no files, or all filenames empty → `400 {"error": "No files uploaded"}`;
  * an upload whose extension is `.pdf` →
    `400 {"error": "PDF files are processed locally in the browser. Use the PDF scan control."}`
    (the whole request is rejected);
  * unsupported image extensions are **skipped silently**;
  * undecodable bytes are **skipped silently**;
  * duplicate uploads (same name + size + content type) are collapsed.
* **Response 200:**
  ```json
  { "pages": [
      { "name": "photo.jpg", "id": "ab12cd34ef56", "width": 1346, "height": 1904 },
      { "name": "broken.png", "error": "…" } ] }
  ```
  `error` entries are per-file scan failures (a single bad photo does not fail
  the batch).
* **Limits:** request body ≤ 50 MB locally (`MAX_CONTENT_LENGTH`);
  JPEG output quality 95.
* **Lifecycle:** artifacts are stored as `<id>.jpg`; the client downloads them
  from `/api/image/<id>`.
* **Local vs Vercel:** on Vercel the body cap is lower (~4.5 MB, enforced by the
  platform) and `/tmp` is ephemeral, so downloads must happen promptly.

---

## POST /api/scan-pdf

Synchronously scans a PDF and returns the result filename. No progress
reporting; the request stays open for the whole scan.

* **Request:** `multipart/form-data`, field `file` (PDF), optional
  `page_limit` (positive integer).
* **Validation:**
  * missing/empty file → `400 {"error": "No file uploaded"}`;
  * extension other than `.pdf` → `400 {"error": "Only PDF files are accepted"}`;
  * `page_limit` < 1 → `400 {"error": "page_limit must be at least 1"}`;
  * a file named `*.pdf` that is not a real PDF fails inside the PDF pipeline →
    `500 {"error": "…processing error…"}`.
* **Response 200:** `{"pdf": "scanned_ab12cd34.pdf"}`
* **Limits:** render DPI 200, JPEG quality 78, uniform A4 pages, no margin.
* **Lifecycle:** temporary input is deleted in a `finally` block; the output PDF
  stays in storage for `/api/pdf/<name>`.
* **Local vs Vercel:** this endpoint is impractical on serverless for large
  PDFs (body cap + function timeout); the job flow or the on-device path is the
  intended choice there.

---

## POST /api/scan-pdf-start

Starts a background scan job and returns immediately.

* **Request:** same as `/api/scan-pdf`.
* **Validation:** same as `/api/scan-pdf`.
* **Response 200:** `{"job_id": "9f8e7d6c5b4a…"}`
* **Lifecycle:**
  1. expired jobs are cleaned up on every call (TTL 600 s, `RSCAN_JOB_TTL`);
  2. the upload is stored as `in_<hex8>.pdf`;
  3. a daemon thread runs the scan and pushes progress events;
  4. when the job finishes, the temporary input is removed;
  5. the assembled PDF is served from `/api/pdf/<scanned_name>.pdf`.
* **Local vs Vercel:** the job store is per-process. A progress request routed
  to another instance answers `404 Job not found`.

---

## GET /api/scan-pdf-progress/<job_id>

Server-Sent Events stream of a job's progress. One JSON object per `data:`
line:

```
data: {"type":"loading"}
data: {"type":"detected","total":12}
data: {"type":"scanning","page":1,"total":12}
data: {"type":"page_done","page":1,"total":12}
data: {"type":"assembling"}
data: {"type":"done","pdf":"scanned_ab12cd34.pdf","elapsed":8.4}
data: {"type":"error","message":"…"}
```

* **Validation:** unknown/expired job → `404 {"error": "Job not found"}`.
* **Frames:** `done`, `error` and the internal `_eof` sentinel end the stream.
  A `: keepalive` comment frame is sent after 30 idle seconds
  (`sse_keepalive_seconds`) so proxies do not close the connection.
* **Semantics:** `page_done` is emitted as pages complete in parallel, so the
  counter is monotonic but not necessarily page order.
* **Client disconnect:** the job keeps running; reconnecting with the same
  `job_id` is possible until the TTL expires.
* **Local vs Vercel:** SSE needs a threaded server (local `app.py` uses
  `threaded=True`) and a platform that does not buffer responses (the route
  sets `X-Accel-Buffering: no`).

---

## GET /api/image/<id>

* **Response 200:** `image/jpeg` (inline).
* **Errors:** missing artifact → `404` with the plain body `not found`
  (this endpoint predates the JSON error shape and the frontend only treats it
  as a failed image load).
* **Local vs Vercel:** best-effort; serverless instances are recycled, so the
  artifact may be gone.

---

## GET /api/pdf/<filename>

* **Validation:** `filename` must equal its own basename and start with
  `scanned_`; anything else → `404 not found`.
* **Response 200:** `application/pdf` as an attachment.
* **Errors:** missing artifact → `404 not found`.

---

## Response/status summary

| Status | Used for |
|---|---|
| 200 | success (including partial success with per-file `error` entries) |
| 400 | invalid upload, wrong file type, bad `page_limit` |
| 404 | unknown job, missing artifact, unknown route (JSON for `/api/*`) |
| 413 | request body over `MAX_CONTENT_LENGTH` (JSON for `/api/*`) |
| 500 | pipeline/PDF failure (message is the sanitised processor error) |

## Changing the API

The frontend clients (`static/js/api/*.js`), `docs/API.md`, and the integration
tests (`tests/integration/test_web_flows.py`) are the three places that must
move together. Prefer additive changes; a breaking change needs a
`CHANGELOG.md` entry under "Changed".
