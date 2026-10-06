/**
 * On-device PDF scan pipeline (shared by both local paths).
 *
 * Flow (in order; pages are processed in chunks of N, N = worker pool size)::
 *
 *   pdf.js render (whole chunk, off the main thread)
 *     -> one scan worker per page (OpenCV.js, in parallel)
 *     -> encode + append in document order (black frame optional)
 *
 * The two callers use different profiles, so behaviour is preserved on both:
 *
 *   /scan-pdf page      -> `PDF_PROFILES.full`     (200 DPI, warm v2 worker,
 *                           uniform A4 pages + frame, JPEG q0.80)
 *   home page fallback  -> `PDF_PROFILES.fallback` (legacy 2x render, light
 *                           worker, page-sized output, JPEG q0.94)
 *
 * Nothing leaves the browser: no fetch, no upload, no server round-trip.
 */

import { LIMITS, PDF_PROFILES, scanPoolSize } from "../../core/constants.js";
import { LocalPdfLimitError } from "../../core/errors.js";
import { logger } from "../../core/logger.js";
import { canKeepThumbnail } from "../../core/state.js";
import { acquireWorkers, enhanceCanvas, planPageChunks, releaseWorkers } from "./pdf-processing.js";
import { appendPage, createOutputDocument, saveOutputDocument } from "./pdf-export.js";
import { openPdfDocument } from "./pdf-engine.js";
import { isSmallScreen, renderPageToCanvas } from "./pdf-renderer.js";

/**
 * @typedef {object} ScanPanel
 * @property {(text: string) => void} title
 * @property {(text: string) => void} beginStep
 * @property {(text?: string) => void} finishStep
 * @property {(text: string) => void} done
 * @property {(total: number) => void} showTotal
 * @property {(page: number) => void} page
 * @property {(done: number, total: number) => void} progress
 */

/**
 * Run a complete on-device PDF scan.
 *
 * @param {File} file
 * @param {number|null} pageLimit null means "all pages"
 * @param {ScanPanel} panel processing-panel controller (progress reporting)
 * @param {object} profile one of `PDF_PROFILES`
 * @returns {Promise<{bytes: Uint8Array, pageImages: Array<{dataUrl: string, width: number, height: number}>}>}
 */
export async function runOnDevicePdfScan(file, pageLimit, panel, profile = PDF_PROFILES.full) {
  if (file.size > LIMITS.maxLocalPdfBytes) {
    throw new LocalPdfLimitError(
      `This PDF is larger than the ${Math.round(LIMITS.maxLocalPdfBytes / (1024 * 1024))} MB local-processing limit.`);
  }

  panel.title("Scanning locally\u2026");
  panel.beginStep("Loading PDF in browser\u2026");

  const source = await openPdfDocument(file);
  panel.finishStep(`Found ${source.numPages} page(s)`);

  if (source.numPages > LIMITS.maxLocalPdfPages) {
    throw new LocalPdfLimitError(
      `This PDF has ${source.numPages} pages. Local scanning supports up to ${LIMITS.maxLocalPdfPages} pages.`);
  }

  const pagesToScan = pageLimit != null ? Math.min(source.numPages, pageLimit) : source.numPages;
  panel.showTotal(pagesToScan);
  panel.title(`Scanning ${pagesToScan} pages\u2026`);

  const poolSize = scanPoolSize({
    pageCount: pagesToScan,
    hardwareConcurrency: navigator.hardwareConcurrency,
    smallScreen: isSmallScreen(),
    profile,
  });
  const { workers, source: workerSource } = await acquireWorkers(profile, poolSize);
  const output = await createOutputDocument();
  const pageImages = [];
  panel.done(`Engine worker ready (${workerSource})${workers.length > 1 ? `, ${workers.length} pages at once` : ""}`);

  try {
    // Pages run in chunks of `workers.length`: render the chunk (pdf.js, off
    // the main thread), scan it with one worker per page, then append those
    // pages in document order. The pool stays saturated, only one chunk of
    // canvases is alive at a time, and pdf-lib always receives pages in order.
    for (const chunk of planPageChunks(pagesToScan, workers.length)) {
      const first = chunk[0];
      const last = chunk[chunk.length - 1];
      panel.beginStep(chunk.length > 1
        ? `Scanning pages ${first}\u2013${last} of ${pagesToScan}\u2026`
        : `Scanning page ${first} of ${pagesToScan}\u2026`);
      panel.page(first);
      panel.progress(first - 1, pagesToScan);

      // 1) render every page of the chunk concurrently
      const rendered = await Promise.all(chunk.map(async (pageNumber) => {
        const pdfPage = await source.getPage(pageNumber);
        const sourcePageSize = pdfPage.getViewport({ scale: 1 });
        const canvas = await renderPageToCanvas(pdfPage, profile);
        return { pageNumber, canvas, sourcePageSize };
      }));

      // 2) scan the whole chunk at once — this is the expensive stage
      await Promise.all(rendered.map((item, index) => enhanceCanvas(item.canvas, workers[index])));

      // 3) encode and append strictly in page order
      for (const item of rendered) {
        const keepPreview = canKeepThumbnail(pageImages.length);
        const preview = await appendPage(output, item.canvas, {
          pageMode: profile.pageMode,
          drawBorder: profile.drawBorder,
          jpegQuality: profile.jpegQuality,
          sourcePageSize: item.sourcePageSize,
          preview: keepPreview,
        });
        if (keepPreview) pageImages.push(preview);
        panel.page(item.pageNumber);
        panel.finishStep(`Page ${item.pageNumber} scanned`);
        panel.progress(item.pageNumber, pagesToScan);
        // Free the bitmap now that the page is embedded: full-size A4
        // canvases are the scan's biggest memory peak.
        item.canvas.width = 0;
        item.canvas.height = 0;
      }
    }

    panel.beginStep("Building PDF\u2026");
    panel.title("Assembling PDF\u2026");
    const bytes = await saveOutputDocument(output);
    panel.finishStep("Done! PDF ready");
    panel.title("Scan complete");
    logger.info("on-device scan finished", { pages: pagesToScan, worker: workerSource });
    return { bytes, pageImages };
  } finally {
    // The warm engine workers must survive (next scan reuses the pool); a
    // per-scan fallback worker is disposable.
    releaseWorkers(workers, { keepAlive: profile.useEngineLoader });
  }
}

/**
 * Validate a local scan request before any work starts (fail fast with a
 * clear message instead of half-scanning).
 *
 * @param {File} file
 * @param {boolean} engineReady whether the full engine has reported ready
 * @param {object} profile
 */
export function assertLocalScanAvailable(file, engineReady, profile) {
  if (profile.useEngineLoader && !engineReady) {
    throw new LocalPdfLimitError(
      "Scan engine is still warming up. Please wait for 'ready' and try again.");
  }
  if (file.size > LIMITS.maxLocalPdfBytes) {
    throw new LocalPdfLimitError(
      `This PDF is larger than the ${Math.round(LIMITS.maxLocalPdfBytes / (1024 * 1024))} MB local-processing limit.`);
  }
}
