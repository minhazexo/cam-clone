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
| `app.py` | New `GET /scan-pdf` → on-device scan page | Unlimited local scans; server never sees the file |
| `vercel.json` | `builds` + `routes` for `@vercel/python` (no `functions` block — Vercel forbids it alongside `builds`; Hobby defaults of 300 s / 2 GB apply automatically) | Standard Python serverless wiring |
| `api/index.py` | (unchanged) re-exports `app` | Vercel Python runtime picks up the `app` variable |
| `scripts/build.ts` | `pdf.worker.js` COPIED verbatim from `pdfjs-dist/legacy` (never bundled) | Rebundling breaks the worker bootstrap (legacy API + modern worker also mismatches) — `getDocument()` then hangs forever with no error |
| `templates/` | Inline SVG favicon on both pages | Kills the `favicon.ico` 404 noise in logs |
| `static/js/{scanpdf,app}.js` | Local caps 250 MB / 250 pages; page-limit modal (10/20/30/40/50/All) on both scan pages | Big local scans; batch control |

## 3. The on-device path (`/scan-pdf`) — why it survives serverless
- Engine = vendored `static/vendor/opencv.js` 4.8.0 (~10 MB) + `scan-worker-v2.js` (full pipeline port) + `scan-geometry.js`, loaded inside a **worker thread** — never parses on the main thread (that froze the page before the fix).
- Warmup: `opencv-loader.js` sends a `{ping}` probe at page open and hands the **warm worker** to the scan flow (no re-parse per scan). Button stays disabled until `ready (v2-full)`; fallback `scan-worker.js` if v2 missing.
- Render at 200-DPI parity (scale 200/72, cap 2500/1800px), q0.80 embed, orientation-matched A4, canvas border frame. Python parity: full-page MAD ≤0.05, sharpness ±0.1% (`bun run parity`).
- `getDocument()` has a 60 s timeout wrapper — a dead pdf.js worker now surfaces an explicit error instead of a silent hang.

## 4. Verified locally (Flask test client, real code paths)
- `GET /` → 200, RScan HTML renders (templates path OK)
- `GET /scan-pdf` → 200 with modal markup + loader/worker script tags
- `GET /api/health` → 200 `{status: ok}`
- `GET /static/...` → 200 for `scanpdf.js`, `scan-worker-v2.js`, `scan-geometry.js`, `opencv-loader.js`, `opencv.js`
- `POST /api/scan` with a synthetic tilted photo → 200, scanned 1035×1464 served back via `/api/image/<id>` → 200 (full image pipeline OK)
- `bun run parity` (worker + geometry + full harnesses) → ALL PASS

## 5. Serverless limits you must know (honest)
- **Request body ~4.5 MB** (Vercel platform cap). `MAX_CONTENT_LENGTH=50MB` applies locally; on Vercel uploads above ~4.5 MB fail at the edge. Keep phone photos <4 MB or downscale client-side. (Browser-local caps are 250 MB / 250 pages — server-independent.)
- **300 s max per request (Hobby default = maximum).** Timings on this codebase: 1 image ≈ 4–5s ✓, 10 PDF pages ≈ 50s ✓, ~30 pages ≈ 3 min ✓, 100 pages ≈ 8–9 min ✗ (>300 s). So: **images + medium PDFs work; 100-page jobs still belong on local `python app.py`.**
- **Ephemeral disk.** `UPLOAD_DIR` is per-instance temp storage. `/api/image/<id>` works if the follow-up hits the same warm instance — with 1 instance it usually does, but treat it as best-effort, not storage.
- **Background threads + SSE** (`/api/scan-pdf-start` → progress stream) function only while the request is alive; the streamed progress UI works for short jobs, not 100-page jobs.
- **Cold start:** first hit loads cv2+numpy+pymupdf (~1–2s). 2 GB default memory keeps it comfortable.
- **First engine load:** ~10 MB WASM through the function, then browser-cached. Expect up to ~30 s “Loading scan engine…” on first visit (page stays responsive).

## 6. Recommended split
- **Vercel:** demo + image scans + small PDFs (≤10 pages). On-device `/scan-pdf` (pdf.js + WASM worker + pdf-lib, zero server) works unlimited anywhere — prefer it for big files.
- **Local / VPS:** full 100-page server scans (`python app.py`), quality gate, CLI batch jobs.

## 7. Env vars (see `.env.example`)
- `PORT` (default 5000, local only — Vercel injects its own), `RSCAN_DEBUG=1` for debug logs. No secrets required.

## 8. Troubleshooting
| Symptom | Cause → fix |
|---|---|
| `Function timeout` on PDF | Too many pages for 300 s → use `/scan-pdf` local flow or fewer pages (page-limit prompt) |
| `413 / request too large` | Over ~4.5 MB upload → compress photo first (server path only) |
| Blank page / 500 on `/` | `templates/` or `static/` missing from deployment → check repo includes them (they're committed) |
| `ImportError: libGL` | `opencv-python` installed instead of headless → `requirements.txt` already pins headless; clear Vercel build cache and redeploy |
| `/api/image/<id>` 404 after scan | Instance recycled between requests → re-scan (ephemeral disk, see §5) |
| `Missing Bun artifact` | `static/vendor/*.js` not committed → run `bun run build` locally, commit, redeploy |
| `/scan-pdf` frozen on open | Old loader parsed 10 MB opencv on main thread → fixed (worker warmup); hard-reload (Ctrl+Shift+R) to drop cached JS |
| Stuck at “Loading PDF in browser…” | Dead pdf.js worker → fixed by verbatim upstream worker + 60 s timeout guard; if it still happens, DevTools Console/Network will now show the worker error — send it back |
| Scan starts with no page options | Stale cached HTML without modal markup → hard-reload; `?v=2` cache-busters are on the script tags |
| Engine stuck “warming up” | WASM compile on slow device can take 60–120 s; page stays usable. Beyond that, console shows the probe error |
