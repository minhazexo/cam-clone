# RScan / Cam-Scanner-Clone — Project Overview (Deep Dive)

Source-grounded overview. Line refs are `file:line`.

## 1. What this project is
- Original RScan: OpenCV document scanner in Python + Java, CamScanner / Microsoft Lens style (`README.md:2-3`).
- This clone adds a full web product: Flask backend + browser UI + server PDF pipeline + local-first PDF/image handling (`app.py:1-8`, `templates/index.html:1-11`, `static/js/app.js`).
- Dual heritage preserved in graph community `Project Docs UI` (README + requirements + index.html, 19 nodes).

## 2. Repository layout (actual)
```
app.py                          # Flask app, all API routes (363 lines)
api/index.py                    # Vercel entrypoint, re-exports app (12 lines)
RScan/Python/scan/
  auto_scan.py                  # main pipeline scan_photo_to_reference (~1103 lines, 37 defs)
  scan.py                       # legacy GCMODE/RMODE/SMODE + globals (225 lines)
  scan_pdf.py                   # PDF/image/dir → scanned PDF (231 lines)
  quality_gate.py               # reference-anchored regression gate (194 lines)
templates/index.html            # upload / processing / results / page-limit modal (147 lines)
static/js/app.js                # 31 frontend functions, 690 lines
static/js/scan-worker.js        # pixel worker, luminance paper/ink model (28 lines)
static/js/runtime.ts            # pdfjs + pdf-lib window bridge (12 lines)
static/vendor/                  # Bun build output: runtime.js + pdf.worker.js (minified, ~3000 graph nodes)
static/css/style.css            # Inter font UI
scripts/build.ts                # Bun build: runtime.ts→esm, pdf.worker.js→iife, browser+minify
scripts/check.ts                # asserts vendor artifacts exist
package.json                    # pdf-lib ^1.17.1, pdfjs-dist 3.11.174, bun scripts
requirements.txt                # flask>=3.0, opencv-python>=5.0, numpy>=1.24, pymupdf>=1.23
vercel.json                     # all routes → api/index.py via @vercel/python
.env.example, LICENSE, bun.lock
IMG-20260905-WA0005.jpg         # outlier: handwritten physics ensemble table, NOT scanner-related
graphify-out/                   # graph.json (3144 nodes), graph.html, GRAPH_REPORT.md
docs/                           # this deep-dive set (you are here)
```

Java sources referenced in README (`RScan/Java/src/scan`, `Main.java`) are **not present** in this checkout — historical only (`README.md:9-12`).

## 3. Tech stack & versions
- Backend: Flask ≥3.0, OpenCV ≥5.0, NumPy ≥1.24, PyMuPDF ≥1.23.
- Original docs cite Python 3.5.4 / OpenCV 3.4.3 and JDK 11 (`README.md:16-18`) — stale, current code needs modern Python (3.10+ tested implicitly by `ThreadPoolExecutor`, type hints).
- Frontend: vanilla JS + pdfjs-dist 3.11.174 (legacy build) + pdf-lib 1.17.1, built with Bun, no framework.
- Deploy: Vercel Python runtime, or `python app.py` → `http://localhost:5000`.

## 4. Entry points
| Entry | File | What happens |
|---|---|---|
| Local dev | `app.py:357-363` | `app.run(host=0.0.0.0, port=PORT/5000, threaded=True)` |
| Vercel | `api/index.py:10` | imports `app` from root |
| CLI single image | `RScan/Python/scan/scan.py:176+` | argparse wrapper |
| CLI PDF | `RScan/Python/scan/scan_pdf.py:196-228` | `--dpi 300 --jpeg-quality 90 --no-trim --no-reframe --output-scale 2.0` |
| Quality gate | `RScan/Python/scan/quality_gate.py:112-190` | compares output vs `reference.png` via `Work Images/` (missing here → gate asserts fail without those assets) |
| Frontend dev | `package.json:7-9` | `bun run build && python app.py` |

## 5. Key constraints (from code)
- `MAX_CONTENT_LENGTH = 50 MB` (`app.py:30`).
- Images allowed: jpg/jpeg/png/bmp/tif/tiff/webp; PDF separate path (`app.py:40-41`).
- `/api/scan` rejects PDFs with 400: "processed locally in browser" (`app.py:114-115`).
- Upload dedup by `(filename, len, content_type)` (`app.py:105-109`).
- Scanned JPGs saved as `{12-hex}.jpg` with quality 95; PDFs as `scanned_{8-hex}.pdf` (`app.py:135-138`, `app.py:283-285`).
- SSE jobs TTL 600s, queue timeout 30s keepalive (`app.py:48`, `app.py:315-319`).
- PDF worker threads: `min(max(1, cpu_count or 4), 8)` (`app.py:265`).
- Serving guards: image IDs must exist; PDFs must start with `scanned_` + basename check (`app.py:335-354`).

## 6. Graph snapshot (honest)
- 3144 nodes / 7911 edges / 125 communities. AST 3119 nodes + semantic 26.
- God nodes (`X`, `S()`, `t()`, …) are all minified pdf.worker/runtime symbols — **not** core abstractions. Real core is `Flask Scan API` (25 nodes), `Auto Scan Core` (27), `Reference Template Alignment` (22), `Frontend Scan UI` (40).
- Most cross-linked project edge: `api_scan() → scan_photo_to_reference()` INFERRED, `app.py → auto_scan.py`.
- Outlier community `Physics Ensemble Notes` (6 nodes, cohesion 0.53) = the JPG physics table, zero links to scanner code.
