/**
 * On-device PDF scan pipeline (shared by both local paths).
 *
 * Flow (per page, in order)::
 *
 *   pdf.js render -> canvas -> scan worker (OpenCV.js) -> enhanced canvas
 *                 -> black frame (optional) -> JPEG -> pdf-lib embed
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

import { LIMITS, PDF_PROFILES } from "../../core/constants.js";
import { LocalPdfLimitError } from "../../core/errors.js";
import { logger } from "../../core/logger.js";
import { canKeepThumbnail } from "../../core/state.js";
import { acquireWorker, enhanceCanvas, releaseWorker } from "./pdf-processing.js";
import { appendPage, createOutputDocument, saveOutputDocument } from "./pdf-export.js";
import { openPdfDocument } from "./pdf-engine.js";
import { renderPageToCanvas } from "./pdf-renderer.js";

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

  const { worker, source: workerSource } = await acquireWorker(profile);
  const output = await createOutputDocument();
  const pageImages = [];
  panel.done(`Engine worker ready (${workerSource})`);

  try {
    for (let pageNumber = 1; pageNumber <= pagesToScan; pageNumber += 1) {
      panel.beginStep(`Scanning page ${pageNumber} of ${pagesToScan}\u2026`);
      panel.page(pageNumber);
      panel.progress(pageNumber - 1, pagesToScan);

      const pdfPage = await source.getPage(pageNumber);
      const sourcePageSize = pdfPage.getViewport({ scale: 1 });
      const canvas = await renderPageToCanvas(pdfPage, profile);
      await enhanceCanvas(canvas, worker);

      const preview = await appendPage(output, canvas, {
        pageMode: profile.pageMode,
        drawBorder: profile.drawBorder,
        jpegQuality: profile.jpegQuality,
        sourcePageSize: { width: sourcePageSize.width, height: sourcePageSize.height },
      });

      if (canKeepThumbnail(pageImages.length)) pageImages.push(preview);
      panel.finishStep(`Page ${pageNumber} scanned`);
      panel.progress(pageNumber, pagesToScan);
    }

    panel.beginStep("Building PDF\u2026");
    panel.title("Assembling PDF\u2026");
    const bytes = await saveOutputDocument(output);
    panel.finishStep("Done! PDF ready");
    panel.title("Scan complete");
    logger.info("on-device scan finished", { pages: pagesToScan, worker: workerSource });
    return { bytes, pageImages };
  } finally {
    // The warm engine worker must survive (next scan reuses it); a
    // per-scan fallback worker is disposable.
    releaseWorker(worker, { keepAlive: profile.useEngineLoader });
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
