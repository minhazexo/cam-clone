# Frontend architecture

Vanilla JavaScript, no framework and no bundler for application code. ES
modules load directly from the templates; the OpenCV.js worker is a classic
script (`importScripts`) because workers cannot use ES modules here.

```
static/js/
  app.js                  entrypoint for /           (composition root)
  scanpdf.js              entrypoint for /scan-pdf   (composition root)
  runtime.ts              built to vendor/runtime.js (pdf.js + pdf-lib globals)
  core/
    constants.js          limits, endpoints, assets, profiles   ← single source
    logger.js             [rscan] logging, debug flag via ?debug=1
    errors.js             AppError hierarchy + toUserMessage()
    dom.js                $, onReady, escapeHtml, safeFilename, downloadUrl, …
    state.js              session state + object-URL lifecycle
  api/
    client.js             fetch + JSON + ApiError normalisation
    scan-api.js           POST /api/scan
    pdf-api.js            start/progress(SSE)/legacy sync/pdfUrl
    health-api.js         GET /api/health (diagnostics)
  ui/
    sections.js           upload / processing / results visibility
    progress.js           processing panel (title, steps, bar, counter)
    modal.js              page-limit modal
    notifications.js      notification seam (native dialogs today)
    results.js            result cards + downloads
    upload-zone.js        drag & drop + file pickers
  features/
    image-scan/image-scan.js         files → server scan → results
    pdf-scan/
      pdf-engine.js                  pdf.js/pdf-lib readiness, document open
      pdf-renderer.js                page → canvas at profile DPI
      pdf-processing.js              worker client (protocol, lifecycle)
      pdf-export.js                  pdf-lib assembly (A4/source, frame)
      pdf-progress.js                SSE events → panel
      server-pdf-scan.js             upload → job → progress → result
      on-device-pdf-scan.js          shared local pipeline (both profiles)
  workers/
    engine-loader.js      warm worker lifecycle (+ legacy window.RScanEngine)
    scan-worker-v2.js     full OpenCV.js pipeline
    scan-worker.js        light fallback enhancer
    scan-geometry.js      geometry port (worker + Node parity harnesses)
```

## Page lifecycle

```
1  HTML parsed (Jinja layout + partials; runtime.js module sets pdfjsLib/PDFLib)
2  page entrypoint module runs (deferred, after runtime.js)
3  init(): wire DOM (upload zone, buttons, modal, panel), start warm-up
4  user drops/picks files
     /          → images: POST /api/scan
                → PDF: page-limit modal → server job + SSE
                       → on failure: on-device pipeline (`fallback` profile)
     /scan-pdf  → page-limit modal → on-device pipeline (`full` profile)
5  results section renders; "Download All" is wired per page
6  "Scan more" resets state, revokes object URLs, shows the upload view
```

`pagehide` on the on-device page terminates the warm worker.

## State management

There is no global store. Two levels:

* **DOM state** — which section is visible (`ui/sections.js`) and what the
  processing panel shows (`ui/progress.js`). Both are the single writers of
  their elements.
* **Session state** (`core/state.js`) — the current results, the dedupe
  signature, the busy flag, and the local PDF object URL. Object URLs are
  created and revoked only here, which is what prevents leaking whole PDFs.

Server data is never mirrored into long-lived client state: the API is
request/response, and progress arrives as events that are rendered immediately.

## Module communication

```
entrypoint (app.js / scanpdf.js)
   │  owns DOM wiring + the decision of which flow to run
   ├──> ui/*          (it tells the UI what to show)
   ├──> features/*    (features run flows; they receive the panel + notify seams)
   │       └──> api/*      (HTTP + SSE)
   │       └──> core/*     (constants, errors, state, dom helpers)
   └──> workers/*     (via features/pdf-scan/pdf-processing.js)
```

Rules:

* `core/` and `api/` never import `ui/` or `features/`.
* `ui/` never imports `features/`.
* Features receive the panel/notify seams as arguments instead of importing UI
  modules — this is what lets the same pipeline serve both pages.
* Only entrypoints touch `document` wiring; everything below is passed elements.

## Worker architecture

See `SCAN_PIPELINE.md` → "Worker protocol". From the frontend's perspective:

* `workers/engine-loader.js` owns worker creation, the ping probe, the v1
  fallback, and the `window.RScanEngine` compatibility global.
* `features/pdf-scan/pdf-processing.js` owns the message exchange and rejects
  the promise on `{error}` or worker death; it never terminates the warm worker
  (only per-scan fallback workers are released).
* Workers are never created per page — one warm worker per page load.

## PDF processing flow (both pages)

```
pdf-upload (zone/picker, ui/upload-zone.js)
  → askPageLimit (ui/modal.js)
  → runServerPdfScan (features/pdf-scan/server-pdf-scan.js)
       startPdfScan → followServerProgress → panel updates → result card
  ↘ on failure
    runOnDevicePdfScan (features/pdf-scan/on-device-pdf-scan.js)
       openPdfDocument → per page: render → enhance → appendPage
       → saveOutputDocument → Blob → state.setLocalPdfBlob
       → ui/results.renderLocalPdfResult | renderLocalPageGrid
```

## DOM contract (ids the modules look up)

| Element | Used by |
|---|---|
| `uploadZone`, `fileInput` | `ui/upload-zone.js` |
| `btnImages`, `btnPdf`, `btnScanMore`, `btnDownloadAll` | entrypoints |
| `engineStatus` | `scanpdf.js` |
| `processingSection`, `procTitle`, `scanLine`, `pageCounter`, `pageCurrent`, `pageTotal`, `progressBarWrap`, `progressBar`, `progressPct`, `stepLog` | `ui/progress.js` |
| `resultsSection`, `resultsGrid` | `ui/sections.js`, `ui/results.js` |
| `pageLimitBackdrop`, `pageLimitOptions`, `pageLimitCancel` | `ui/modal.js` |

Ids are defined in `templates/partials/*` and `templates/layouts/base.html`.
`tests/js/assets.test.js` guards asset paths; the integration tests assert these
ids are present in the rendered HTML.

## CSS

`static/css/style.css` is the only stylesheet (design tokens, layout, components).
Result cards are generated by `ui/results.js` using the class names in that
file (`result-card`, `result-card-img`, `result-card-body`, `result-card-name`,
`result-card-meta`, `result-card-actions`, `result-card-pdf`). Changing one
without the other breaks the look.
