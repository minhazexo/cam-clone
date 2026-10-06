/**
 * pdf.js / pdf-lib availability.
 *
 * `static/vendor/runtime.js` (built by `bun run build` from
 * `static/js/runtime.ts`) assigns `window.pdfjsLib` and `window.PDFLib` when it
 * executes. That script is loaded before the page entrypoint in
 * `templates/layouts/base.html`, but a slow/cached page can still race it, so
 * this module waits briefly instead of throwing.
 */

import { ASSETS, LIMITS } from "../../core/constants.js";
import { EngineUnavailableError } from "../../core/errors.js";
import { logger } from "../../core/logger.js";

const POLL_INTERVAL_MS = 50;
const POLL_TIMEOUT_MS = 10000;

/** Have pdf.js and pdf-lib finished loading? */
export function isPdfEngineReady() {
  return Boolean(window.pdfjsLib && window.PDFLib);
}

/**
 * Resolve once pdf.js + pdf-lib are available.
 *
 * @returns {Promise<{pdfjsLib: object, PDFLib: object}>}
 * @throws {EngineUnavailableError} when they never appear
 */
export function ensurePdfEngine() {
  if (isPdfEngineReady()) {
    configurePdfWorker();
    return Promise.resolve({ pdfjsLib: window.pdfjsLib, PDFLib: window.PDFLib });
  }

  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (isPdfEngineReady()) {
        clearInterval(timer);
        configurePdfWorker();
        resolve({ pdfjsLib: window.pdfjsLib, PDFLib: window.PDFLib });
        return;
      }
      if (Date.now() - started > POLL_TIMEOUT_MS) {
        clearInterval(timer);
        logger.error("pdf.js/pdf-lib never loaded", ASSETS.runtime);
        reject(new EngineUnavailableError(
          "The local PDF engine did not load. Reload the page and try again."));
      }
    }, POLL_INTERVAL_MS);
  });
}

/** Point pdf.js at the vendored worker (never rebundled — see scripts/build.ts). */
export function configurePdfWorker() {
  if (window.pdfjsLib && window.pdfjsLib.GlobalWorkerOptions) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = ASSETS.pdfWorker;
  }
}

/**
 * Open a PDF document from a File, with a timeout.
 *
 * A hung pdf.js worker otherwise stalls the UI forever with no error, so the
 * timeout turns it into an actionable message (kept from the original
 * implementation).
 *
 * @param {File} file
 * @returns {Promise<object>} pdf.js document proxy
 */
export async function openPdfDocument(file) {
  const { pdfjsLib } = await ensurePdfEngine();
  const bytes = new Uint8Array(await file.arrayBuffer());

  return new Promise((resolve, reject) => {
    let settled = false;
    let task = null;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try {
        if (task && task.destroy) task.destroy();
      } catch (error) {
        logger.debug("pdf task destroy failed", error);
      }
      reject(new EngineUnavailableError(
        `PDF load timed out after ${Math.round(LIMITS.pdfLoadTimeoutMs / 1000)}s. ` +
        `The pdf.js worker (${ASSETS.pdfWorker}) is probably blocked — ` +
        "check DevTools Console/Network for worker errors."));
    }, LIMITS.pdfLoadTimeoutMs);

    try {
      task = pdfjsLib.getDocument({ data: bytes });
    } catch (error) {
      settled = true;
      clearTimeout(timer);
      reject(error);
      return;
    }

    task.promise.then(
      (doc) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(doc);
      },
      (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(error instanceof Error
          ? error
          : new EngineUnavailableError(`Could not open PDF: ${String(error)}`));
      },
    );
  });
}
