/**
 * Single source of truth for frontend limits, endpoints, quality values and
 * worker paths.
 *
 * Rules:
 *  - never hardcode an `/api/...` URL or a `/static/...` asset path elsewhere;
 *  - never restate a limit (bytes, pages, thumbnails) in a feature module;
 *  - the backend mirrors these limits in `rscan/config/settings.py`. If you
 *    change one side, change the other and update `docs/API.md`.
 */

/** HTTP API endpoints. Functions take the already-validated path segment. */
export const ENDPOINTS = {
  health: "/api/health",
  scan: "/api/scan",
  scanPdf: "/api/scan-pdf",
  scanPdfStart: "/api/scan-pdf-start",
  scanPdfProgress: (jobId) => `/api/scan-pdf-progress/${encodeURIComponent(jobId)}`,
  image: (id) => `/api/image/${encodeURIComponent(id)}`,
  pdf: (name) => `/api/pdf/${encodeURIComponent(name)}`,
};

/** Static assets that must stay in sync with the templates and the worker. */
export const ASSETS = {
  runtime: "/static/vendor/runtime.js",
  pdfWorker: "/static/vendor/pdf.worker.js",
  opencv: "/static/vendor/opencv.js",
  /** Full pipeline worker (OpenCV.js + geometry) — see docs/SCAN_PIPELINE.md. */
  scanWorkerV2: "/static/js/workers/scan-worker-v2.js",
  /** Legacy light enhancer used when the full engine cannot load. */
  scanWorkerFallback: "/static/js/workers/scan-worker.js",
};

/** Client-side limits (mirrored by the server settings). */
export const LIMITS = {
  /** Largest PDF the browser will process locally (250 MB). */
  maxLocalPdfBytes: 250 * 1024 * 1024,
  /** Largest page count the browser will process locally (250). */
  maxLocalPdfPages: 250,
  /** `null` means "all pages" for the page-limit modal. */
  defaultPageLimit: null,
  /** Thumbnails kept for the results grid (memory guard). */
  maxThumbnails: 12,
  /** How long to wait for pdf.js before giving the user an actionable error. */
  pdfLoadTimeoutMs: 60000,
};

/** `accept` attribute values for the file pickers. */
export const ACCEPT = {
  images: ".jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp",
  all: ".jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp,.pdf",
  pdfOnly: ".pdf",
};

/** Page-limit choices offered by the modal (data-limit values). */
export const PAGE_LIMIT_OPTIONS = [10, 20, 30, 40, 50, "all"];

/**
 * On-device PDF scan profiles.
 *
 * Two profiles exist because the product has two local paths, and their
 * output intentionally differs:
 *
 *  - `full`     the `/scan-pdf` page: 200 DPI (server parity), warm full
 *               engine, uniform A4 pages with the black frame, JPEG q0.80.
 *  - `fallback` the home page's last-resort path when the server flow fails:
 *               legacy behaviour preserved (page-sized output, no frame,
 *               JPEG q0.94, light worker). It must stay cheap and instant.
 *
 * Both run through the same pipeline code; only these values differ.
 */
export const PDF_PROFILES = {
  full: {
    name: "full",
    /** Render resolution: 200 DPI == 200/72 CSS scale, width-capped for memory. */
    renderDpi: 200,
    capWidthLarge: 2500,
    capWidthSmall: 1800,
    smallScreenMaxWidth: 768,
    /** `null` scale means "use renderDpi"; fallback uses a plain 2x cap. */
    fallbackScaleCap: null,
    fallbackFitWidth: null,
    /** Warm worker from the engine loader (falls back to the light worker). */
    useEngineLoader: true,
    jpegQuality: 0.8,
    /** "a4" -> uniform framed pages; "source" -> the PDF's own page size. */
    pageMode: "a4",
    drawBorder: true,
    downloadNameSuffix: ".pdf",
  },
  fallback: {
    name: "fallback",
    renderDpi: null,
    capWidthLarge: null,
    capWidthSmall: null,
    smallScreenMaxWidth: 0,
    fallbackScaleCap: 2.0,
    fallbackFitWidth: 1500,
    useEngineLoader: false,
    jpegQuality: 0.94,
    pageMode: "source",
    drawBorder: false,
    downloadNameSuffix: ".pdf",
  },
};

/** A4 page sizes in PDF points, matched to the image orientation. */
export const A4_PAGE = {
  portrait: [595, 842],
  landscape: [842, 595],
};

/** Frame stroke width as a fraction of the page's short side (matches server). */
export const PAGE_BORDER_STROKE_RATIO = 0.003;
