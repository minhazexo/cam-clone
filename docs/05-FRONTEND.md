# Frontend Deep Dive (`templates/index.html` + `static/js/app.js` + workers)

## 1. Page structure (`index.html` 147 lines)
- Head: Inter font, `style.css`, meta description "CamScanner-style".
- Header: RScan logo SVG + tagline.
- `#uploadSection`: drop zone, `fileInput (multiple, .jpg/.jpeg/.png/.bmp/.tif/.tiff/.webp/.pdf)`, `btnImages` / `btnPdf`, "PDF processed on server — no cloud storage".
- `#processingSection.hidden`: scanner-doc SVG + `#scanLine`, `#procTitle`, `#pageCounter (current/total)`, `#progressBarWrap`, `#stepLog (aria-live)`.
- `#resultsSection.hidden`: `resultsGrid`, `btnDownloadAll`, `btnScanMore`.
- Footer: "Python + OpenCV + Flask".
- `#pageLimitBackdrop` modal: title, input, `onOption/onCancel/onBackdrop`.

## 2. `app.js` — 31 functions, 690 lines
Upload/dispatch: `handleFiles, scanPdfLocally, scanPdfWithLiveProgress, askPageLimit, limit, onOption, onCancel, onBackdrop`
Progress UI: `showProcessing, showUpload, resetProcessingUI, updateProcTitle, addStep, markStepDone, showPageCounter, setPageCurrent, showProgressBar, updateProgressBar, setScanLine`
Results: `showImageResults, showServerPdfResult, showLocalPdfResult, downloadAll, clearLocalPdf`
Utils: `formatBytes, safeFilename, esc, dataUrlToBytes, enhanceCanvas, closeEventSource, cleanup`
- Image path: `handleFiles(images)` → `POST /api/scan` → `showImageResults` (thumbs from `/api/image/<id>`).
- Server PDF: `scanPdfWithLiveProgress` → `POST /api/scan-pdf-start` → `EventSource(/api/scan-pdf-progress/<job>)` → step log + counter → `showServerPdfResult` (link `/api/pdf/<name>`).
- Local PDF: `scanPdfLocally` — pdfjs per-page render → `enhanceCanvas` (posts ImageData to `scan-worker.js`) → pdf-lib `PDFDocument` assemble → blob URL → `showLocalPdfResult`. `clearLocalPdf` revokes URLs. `closeEventSource` + `cleanup` reset state.
- `askPageLimit` modal gates large PDFs before either PDF path.

## 3. `scan-worker.js` (28 lines, local-only, no network)
`onmessage({width,height,pixels})` → per-pixel luminance blend (paper/ink model) → `postMessage({width,height,pixels}, transfer)`. See ARCHITECTURE for formula.

## 4. `runtime.ts` (12 lines) + vendor
Imports `pdfjs-dist/legacy/build/pdf.js` + `pdf-lib`, sets `workerSrc=/static/vendor/pdf.worker.js`, assigns `window.pdfjsLib` / `window.PDFLib` for `app.js`.
Built by `scripts/build.ts` (Bun, browser, minify, external sourcemap) into `static/vendor/`; verified by `scripts/check.ts`. These two minified outputs dominate the knowledge graph — see GRAPH_KNOWLEDGE_MAP.

## 5. Local full-quality path (`/scan-pdf` + opencv.js)
`templates/scan_pdf.html` + `static/js/scanpdf.js` + `static/js/opencv-loader.js` + vendored `static/vendor/opencv.js` (4.8.0, ~10 MB, lazy-loaded with CDN fallback) + workers `scan-worker-v2.js` (photometry + full `processPage`) and `scan-geometry.js` (geometry port). Same `{width,height,pixels}` worker protocol as v1 (falls back to v1 if v2 missing). Render at 200-DPI parity (scale 200/72, cap 2500/1800px), q0.80 embed, orientation-matched A4, canvas border frame. Parity vs Python: full-page MAD ≤0.05, sharpness ±0.1%, ~8.5 s/page WASM. Details + gates: `09-LOCAL-FULL-QUALITY-PLAN.md`, harnesses `tests/parity_*.js`, fixtures `scripts/gen_fixtures.py`.
