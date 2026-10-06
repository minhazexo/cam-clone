# Deployment

RScan runs in two places: a local Flask process and Vercel serverless
functions. Both use the same `create_app()` factory.

## Local

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                     # headless OpenCV, no libGL needed
python app.py                                       # → http://localhost:5000
```

* `PORT` (default 5000) — HTTP port.
* `RSCAN_DEBUG=1` — verbose logs + Flask debug mode.
* `RSCAN_UPLOAD_DIR` — artifact directory (default `<system temp>/rscan_uploads`).
* `RSCAN_JOB_TTL` — seconds an SSE job is kept (default 600).

The dev server runs threaded (`threaded=True`), which is required for SSE
streaming plus background scan threads. A production WSGI server works too, as
long as it is multi-threaded (e.g. `gunicorn -w 1 -k gthread --threads 8 app:app`).

Local capabilities:

| Concern | Local |
|---|---|
| Request body | 50 MB (`MAX_CONTENT_LENGTH`) |
| Request time | unlimited |
| Disk | your machine (`/tmp/rscan_uploads` by default) |
| Large PDFs | server flow ✔, on-device flow ✔ |
| Jobs | in-memory, TTL 600 s |

## Vercel

`vercel.json` builds `api/index.py` with `@vercel/python` and routes every path
to it:

```json
{ "builds": [{ "src": "api/index.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "api/index.py" }] }
```

Steps:

1. Import the repository in Vercel (framework: **Other**, root: repo root).
2. No build command is required — the vendor artifacts are committed.
3. Deploy, then verify:
   `https://<project>.vercel.app/api/health` → `{"status": "ok", "service": "rscan"}`.
4. Open `/scan-pdf` and wait for **“Scan engine ready (v2-full)”**.

`api/index.py` is the only file that manipulates `sys.path` (Vercel's legacy
Python builder does not guarantee the deployment root is importable). Template
and static folders are absolute, so the app does not depend on the working
directory.

### Serverless limits (honest matrix)

| Concern | Local | Vercel Hobby |
|---|---|---|
| Request body | 50 MB | ~4.5 MB |
| Function time | unlimited | ~60 s |
| Disk | persistent-ish | ephemeral `/tmp`, per instance |
| Job store | one process | one process *per instance* |
| Large PDF scans | ✔ | use `/scan-pdf` (on-device) |
| Image scans | ✔ | ✔ small batches |
| Result download | ✔ | best-effort (artifact may be evicted) |

The on-device path (`/scan-pdf`) never touches the server, so it is unaffected
by all of the above. That is the intended answer for large documents in
production.

### Resources

The Python function needs roughly: NumPy + OpenCV headless (~90 MB) + PyMuPDF.
If a deployment exceeds the platform's bundle limits, split scanning into a
separate function or move to a container host — the layering already allows it
(everything is behind `create_app()` / the service layer).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | local HTTP port |
| `RSCAN_DEBUG` | `0` | `1` → debug logging + Flask debug |
| `RSCAN_UPLOAD_DIR` | `<temp>/rscan_uploads` | artifact directory |
| `RSCAN_JOB_TTL` | `600` | seconds a job (and its artifacts) is retained |

No API keys, no third-party services, no database. `.env.example` documents the
same list; never commit a real `.env`.

## Post-deploy verification

```bash
curl -s https://<project>.vercel.app/api/health
# {"service":"rscan","status":"ok"}
```

Then, in the browser: scan one image, run one small server PDF scan (watch the
SSE steps), and run one `/scan-pdf` scan. If SSE shows `Job not found`, the
progress request landed on a different instance — see the limits table.

## Operational notes

* **Logs:** INFO by default (`rscan.*` loggers). Background jobs log with their
  `job_id`, so `grep <job_id>` reconstructs a scan.
* **Artifacts:** `<temp>/rscan_uploads`; safe to delete between runs. Nothing
  is kept beyond the job TTL on the server.
* **Scaling:** the job store is per process. Multiple instances (or multiple
  workers) would need a shared store — the abstraction is `JobStore`, and the
  injection point is `rscan/web/app_factory.create_app`.
* **Security:** no secrets, no outbound calls, uploads are validated by
  extension and decoded defensively. Report issues per `SECURITY.md`.
