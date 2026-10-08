# API Reference (Deep Dive, from `app.py`)

Base: `http://localhost:5000`. All JSON unless noted. Max body 50 MB.

## `GET /` (`app.py:87-89`)
Renders `templates/index.html`.

## `POST /api/scan` (`app.py:92-147`) — images only
- Form: `files` (multi). Dedup key `(filename, len, content_type)`.
- PDF extension → `400 {error: "PDF files are processed locally..."}`.
- Non-image ext skipped silently; undecodable → skipped; scan exception → `{name, error}` entry.
- Success per file: decode → `scan_photo_to_reference(img)` → JPG q95 → `{12-hex}.jpg` in `UPLOAD_DIR` → `{name, id, width, height}`.
- Returns `{pages: [...]}`. Empty upload → `400 {error: "No files uploaded"}`.

## `POST /api/scan-pdf` (`app.py:152-194`) — legacy sync
- Form: `file` (.pdf only), optional `page_limit>=1`.
- Writes `in_{8-hex}.pdf`, calls `scan_pdf_to_reference(in, out, page_limit)`, removes input, returns `{pdf: "scanned_{8-hex}.pdf"}`.
- Errors: `400` no file / non-PDF / bad limit; `500` scan fail (logged with elapsed).

## `POST /api/scan-pdf-start` (`app.py:199-233`) — async SSE start
- Same validation. Saves input, `_new_job()` → spawns daemon `_scan_pdf_worker`, returns `{job_id}` immediately. Cleans jobs >600s first.

## `GET /api/scan-pdf-progress/<job_id>` (`app.py:303-332`) — SSE stream
- `404 {error: "Job not found"}` if unknown.
- Events (`_scan_pdf_worker`, `app.py:247-300`):
  `loading` → `detected {total}` → `scanning {page:1,total}` → `page_done {page,total}` ×N → `assembling` → `done {pdf, elapsed}` | `error {message}` → `_eof` (closes).
- Transport: `text/event-stream`, `no-cache`, `X-Accel-Buffering: no`, 30s `: keepalive` comments.

## `GET /api/image/<file_id>` (`app.py:335-341`)
Serves `{UPLOAD_DIR}/{file_id}.jpg` as `image/jpeg`, else `404 "not found"`.

## `GET /api/pdf/<filename>` (`app.py:344-354`)
Basename + `startswith("scanned_")` guard, serves PDF as attachment, else 404.

## Operational details
- `UPLOAD_DIR = {tempdir}/rscan_uploads` (`app.py:37-38`). IDs uuid4 hex.
- Logging `rscan.app` / `rscan.scan_pdf`, DEBUG if `RSCAN_DEBUG=1` else INFO.
- Threads: Flask `threaded=True`; PDF pages `ThreadPoolExecutor(min(max(1,cpu or 4),8))`.
- Graph edges confirm: `api_scan→scan_photo_to_reference`, `_scan_pdf_worker→collect_pages/save_bgr_pages_as_pdf`, `api_scan_pdf→scan_pdf_to_reference` (Surprising Connections, all INFERRED but code-verified).
