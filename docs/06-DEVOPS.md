# DevOps, Deployment & Maintenance

## 1. Local run
```
pip install -r requirements.txt   # flask, opencv-python, numpy, pymupdf
bun run build                     # Bun → static/vendor/runtime.js + pdf.worker.js
python app.py                     # → http://localhost:5000
# or: bun run dev  (build + python app.py)
bun run scripts/check.ts          # verify vendor artifacts
```
Env: `PORT` (default 5000), `RSCAN_DEBUG=1` for DEBUG logs. No API keys needed.

## 2. Vercel (`vercel.json`, `api/index.py`)
- `version:2`, one build `api/index.py → @vercel/python`, route `/(.*) → api/index.py`.
- `api/index.py` inserts repo root into `sys.path`, `from app import app`. Stateless caveat: `UPLOAD_DIR` (tempdir) + in-memory `_job_store` do not persist across serverless instances — long SSE PDF jobs are best on a stateful host.

## 3. Dependencies (exact pins in repo)
- `requirements.txt`: flask>=3.0, opencv-python>=5.0, numpy>=1.24, pymupdf>=1.23.
- `package.json`: name `rscan-smart-scanner` 0.1.0, deps `pdf-lib ^1.17.1`, `pdfjs-dist 3.11.174`, dev `bun-types latest`.

## 4. Runtime dirs & hygiene
- Uploads: `{tempdir}/rscan_uploads`, auto-created. Temp inputs `in_*.pdf` removed in `finally`; outputs kept (no auto-purge except 600s job-record TTL — disk can grow, add cron purge if needed).
- Logs: `rscan.app` + `rscan.scan_pdf`, include bytes/page_limit/elapsed per PDF.

## 5. Known gaps / TODOs (from code + graph)
- `Work Images/` assets missing → `quality_gate.py` cannot run here; re-add `pdf photo..jpg` + `reference.png` to use the gate.
- Java `RScan/Java` absent (README history only).
- 26 isolated nodes + 58 thin communities in graph: mostly `package.json`/`vercel.json` leaves + single-use helpers — expected, not bugs.
- `IMG-20260905-WA0005.jpg` physics table is unrelated — move out of root or delete to de-noise future graphs.
- No auth/rate-limit; add reverse-proxy limits before public hosting (50 MB body already set).
