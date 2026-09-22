# Vercel Deployment Guide — RScan / Cam-Scanner-Clone

## 1. Deploy steps (2 min)
1. Push repo to GitHub (done: `minhazexo/cam-clone`, branch `master`).
2. Vercel → Add New Project → import the repo. Framework preset: **Other**. Root directory: repo root.
3. No build command needed (no `vercel-build` step; frontend vendor files in `static/vendor/` are prebuilt — if missing, run `bun run build` locally and commit them).
4. Deploy. Open `https://<project>.vercel.app/api/health` — expect `{"status":"ok","service":"rscan"}`.

## 2. What changed to become deploy-ready
| File | Change | Why |
|---|---|---|
| `requirements.txt` | `opencv-python` → `opencv-python-headless>=4.8` | Server has no libGL; headless is drop-in (repo has zero GUI calls — verified) |
| `app.py` | Absolute `template_folder`/`static_folder` from `__file__` | Serverless cwd is not repo root; relative paths break template/static serving |
| `app.py` | New `GET /api/health` → `{status, service}` | Liveness probe + post-deploy check |
| `vercel.json` | Added `functions.api/index.py: {maxDuration: 60, memory: 1024}` | Cap runtime (Hobby max 60s), give OpenCV headroom |
| `api/index.py` | (unchanged) re-exports `app` | Vercel Python runtime picks up the `app` variable |

## 3. Verified locally (Flask test client, real code paths)
- `GET /` → 200, RScan HTML renders (templates path OK)
- `GET /api/health` → 200 `{status: ok}`
- `GET /static/js/app.js` → 200 (static serving OK)
- `POST /api/scan` with a synthetic tilted photo → 200, scanned 1035×1464 served back via `/api/image/<id>` → 200 (full image pipeline OK)

## 4. Serverless limits you must know (honest)
- **Request body ~4.5 MB** (Vercel platform cap). `MAX_CONTENT_LENGTH=50MB` applies locally; on Vercel uploads above ~4.5 MB fail at the edge. Keep phone photos <4 MB or downscale client-side.
- **60s max per request (Hobby).** Timings on this codebase: 1 image ≈ 4–5s ✓, 10 PDF pages ≈ 50s (borderline!), 100 pages ≈ 8–9 min ✗. So: **images + small PDFs work; big PDFs will time out.**
- **Ephemeral disk.** `UPLOAD_DIR` is per-instance temp storage. `/api/image/<id>` works if the follow-up hits the same warm instance — with 1 instance it usually does, but treat it as best-effort, not storage.
- **Background threads + SSE** (`/api/scan-pdf-start` → progress stream) function only while the request is alive; the streamed progress UI works for short jobs, not 100-page jobs.
- **Cold start:** first hit loads cv2+numpy+pymupdf (~1–2s). `memory: 1024` keeps it comfortable.

## 5. Recommended split
- **Vercel:** demo + image scans + small PDFs (≤10 pages). Local-first browser PDF path (`scanPdfLocally`, pdf.js + pdf-lib, zero server) works unlimited anywhere — prefer it for big files.
- **Local / VPS:** full 100-page server scans (`python app.py`), quality gate, CLI batch jobs.

## 6. Env vars (see `.env.example`)
- `PORT` (default 5000, local only — Vercel injects its own), `RSCAN_DEBUG=1` for debug logs. No secrets required.

## 7. Troubleshooting
| Symptom | Cause → fix |
|---|---|
| `Function timeout` on PDF | Too many pages for 60s → use local scan or fewer pages (`page_limit` prompt) |
| `413 / request too large` | Over ~4.5 MB upload → compress photo first |
| Blank page / 500 on `/` | `templates/` or `static/` missing from deployment → check repo includes them (they're committed) |
| `ImportError: libGL` | `opencv-python` installed instead of headless → `requirements.txt` already pins headless; clear Vercel build cache and redeploy |
| `/api/image/<id>` 404 after scan | Instance recycled between requests → re-scan (ephemeral disk, see §4) |
| `Missing Bun artifact` | `static/vendor/*.js` not committed → run `bun run build` locally, commit, redeploy |
