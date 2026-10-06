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

/**
 * On-device scan worker pool.
 *
 * The scan stage is ~90% of the per-page cost of a local PDF scan (measured
 * server-side on an A4 page at 200 DPI: ~3.9 s scanning vs ~0.6 s encoding
 * and ~0.02 s rendering), and it runs entirely inside a Web Worker. Running
 * several workers therefore turns cores into scanned pages: N workers scan N
 * pages at once, while pdf.js rendering and JPEG encoding keep going on the
 * main thread.
 *
 * The caps exist because every worker owns a full copy of the ~10 MB
 * OpenCV.js engine plus the intermediate Mats of one A4 page, so the cap is a
 * memory guard rather than a CPU one: small screens get fewer workers, and
 * one core is only kept back for rendering/encoding when the machine has a
 * spare one to give (below 8 cores every core scans).
 */
export const SCAN_POOL = {
  /** Hard cap on concurrently warm OpenCV.js workers (memory guard). */
  maxWorkers: 6,
  /** Small screens: fewer workers, more headroom for render + encode. */
  maxWorkersSmallScreen: 3,
  /** Cores kept free for pdf.js rendering, JPEG encoding and the UI … */
  reservedCores: 1,
  /** … but only from this many cores upwards (see `usableCores`). */
  spareCoreThreshold: 8,
  /** Used when the browser hides `navigator.hardwareConcurrency`. */
  fallbackCores: 4,
};

/**
 * Cores the scan stage may use: keep one back for render/encode/UI only when
 * there is a spare (on a 4-core phone all four should be scanning).
 *
 * @param {number} cores
 * @returns {number}
 */
export function usableCores(cores) {
  return cores >= SCAN_POOL.spareCoreThreshold
    ? Math.max(1, cores - SCAN_POOL.reservedCores)
    : Math.max(1, cores);
}

/**
 * Decide how many scan workers a local scan should run with, and *why* — the
 * reason is surfaced in the UI so "only N pages at once" is never a mystery.
 *
 * Pure policy (unit-tested in `tests/js/helpers.test.js`); spawns nothing.
 *
 * @param {{pageCount: number, hardwareConcurrency?: number,
 *          smallScreen?: boolean, profile?: {useEngineLoader?: boolean}}} options
 * @returns {{workers: number, reason: string}}
 */
export function scanPoolPlan({ pageCount, hardwareConcurrency, smallScreen, profile }) {
  // The home page's fallback profile uses a disposable light worker and must
  // stay instant and unchanged — one worker, exactly as before.
  if (!profile || !profile.useEngineLoader) {
    return { workers: 1, reason: "fallback profile uses a single light worker" };
  }
  // A single page has nothing to overlap (and no reason to spawn engines).
  if (!Number.isFinite(pageCount) || pageCount < 2) {
    return { workers: 1, reason: "only one page to scan" };
  }

  const cores = Number.isFinite(hardwareConcurrency) && hardwareConcurrency > 0
    ? hardwareConcurrency
    : SCAN_POOL.fallbackCores;
  const usable = usableCores(cores);
  const cap = smallScreen ? SCAN_POOL.maxWorkersSmallScreen : SCAN_POOL.maxWorkers;
  const workers = Math.max(1, Math.min(pageCount, cap, usable));

  // Name the constraint that actually bound the pool (most restrictive first).
  let reason;
  if (workers >= pageCount) reason = `only ${pageCount} page${pageCount === 1 ? "" : "s"}`;
  else if (workers === usable) reason = `${usable} core${usable === 1 ? "" : "s"}`;
  else if (workers === cap) reason = smallScreen ? "small screen" : "memory cap";
  else reason = "unknown";
  if (workers === 1 && usable === 1) reason = "single CPU core";

  return { workers, reason };
}
