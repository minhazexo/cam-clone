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

import { LIMITS, PDF_PROFILES, scanPoolPlan } from "../../core/constants.js";
import { EngineUnavailableError, LocalPdfLimitError } from "../../core/errors.js";
import { logger } from "../../core/logger.js";
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

  const plan = scanPoolPlan({
    pageCount: pagesToScan,
    hardwareConcurrency: navigator.hardwareConcurrency,
    smallScreen: isSmallScreen(),
    profile,
  });
  let poolSize = plan.workers;
  const firstAcquire = await acquireWorkers(profile, poolSize);
  let workers = firstAcquire.workers;
  // The pool may warm fewer workers than requested (a spare can fail to
  // compile its WASM engine). Drive batching off the actual pool from here
  // on so `workers[index]` always exists.
  poolSize = workers.length;
  if (poolSize < 1) {
    throw new EngineUnavailableError("Scan engine failed to start. Try again, or use the server scan.");
  }
  const workerSource = firstAcquire.source;
  const output = await createOutputDocument();
  const pageImages = [];
  const poolLabel = workers.length > 1
    ? `${workers.length} pages at once (${plan.reason})`
    : `1 page at a time (${plan.reason})`;
  panel.done(`Engine worker ready (${workerSource}) — ${poolLabel}`);
  logger.debug("scan pool plan", {
    workers: workers.length, reason: plan.reason, pages: pagesToScan,
    cores: navigator.hardwareConcurrency, smallScreen: isSmallScreen(),
  });

  /** Render one chunk (pdf.js, off the main thread), then scan it with the pool. */
  async function prepareChunk(chunk) {
    const rendered = await Promise.all(chunk.map(async (pageNumber) => {
      const pdfPage = await source.getPage(pageNumber);
      const sourcePageSize = pdfPage.getViewport({ scale: 1 });
      const canvas = await renderPageToCanvas(pdfPage, profile);
      return { pageNumber, canvas, sourcePageSize };
    }));
    // One in-flight message per worker: the pool scans this chunk alone, so
    // no worker ever receives a second request before answering the first.
    // Sliced by the CURRENT pool size so a batch sized for an older, larger
    // pool (see the engine-fault retry below) can never index past `workers`.
    const stride = Math.max(1, workers.length);
    for (let at = 0; at < rendered.length; at += stride) {
      const slice = rendered.slice(at, at + stride);
      await Promise.all(slice.map((item, index) => enhanceCanvas(item.canvas, workers[index])));
    }
    return rendered;
  }

  let cursor = 1;
  /** Next batch of pages for the CURRENT pool size (re-sized after recovery). */
  function takeBatch() {
    const rest = pagesToScan - cursor + 1;
    if (rest <= 0) return [];
    const [batch] = planPageChunks(rest, Math.max(1, workers.length));
    cursor += batch.length;
    const offset = cursor - batch.length - 1;
    return batch.map((page) => page + offset);
  }
  const firstBatch = takeBatch();
  panel.beginStep(firstBatch.length > 1
    ? `Scanning pages 1\u2013${firstBatch[firstBatch.length - 1]} of ${pagesToScan}\u2026`
    : `Scanning page 1 of ${pagesToScan}\u2026`);
  let currentBatch = firstBatch;
  // Scan the *next* chunk while this one is encoded and appended. The workers
  // are separate threads, so scanning keeps running while the main thread
  // embeds pages — and only one chunk holds the pool at a time, so ordering
  // stays strict: chunk i is always fully appended before chunk i + 1.
  let pendingScan = prepareChunk(currentBatch);

  try {
    for (;;) {
      let scanned;
      try {
        scanned = await pendingScan;
      } catch (error) {
        if (!error || !error.engineFault) throw error;
        // A worker's WASM engine threw an uncaught C++ exception (OpenCV
        // assertion or out-of-memory) and is left unusable. Drop the whole
        // pool, warm a smaller fresh one and re-run this batch; each retry
        // shrinks the pool, so persistent pressure degrades to one worker
        // instead of failing the scan outright.
        logger.warn("scan pool faulted; restarting with fresh workers", {
          message: error.message, poolSize,
        });
        releaseWorkers(workers, { discard: true });
        if (poolSize <= 1) {
          throw new EngineUnavailableError(
            `${error.message}. The local scan could not recover \u2014 try again, or use the server scan.`);
        }
        poolSize = Math.max(1, poolSize - 1);
        workers = (await acquireWorkers(profile, poolSize)).workers;
        // The fresh pool may hold fewer workers than requested, so sync to
        // the actual pool and re-batch: `currentBatch` was sized for the
        // old, larger pool and indexing it directly left `workers[index]`
        // undefined (`Cannot set properties of undefined (setting
        // 'onmessage')`). Rewind the cursor and take the head for the new
        // pool; the tail is picked up by later `takeBatch()` calls.
        poolSize = workers.length;
        if (poolSize < 1) {
          throw new EngineUnavailableError(
            `${error.message}. The local scan could not recover \u2014 try again, or use the server scan.`);
        }
        cursor -= currentBatch.length;
        if (cursor < 1) cursor = 1;
        currentBatch = takeBatch();
        panel.done(`Scan engine faulted \u2014 restarting with ${poolSize} worker${poolSize === 1 ? "" : "s"}…`);
        pendingScan = prepareChunk(currentBatch);
        continue;
      }

      // Start the next chunk's render+scan *before* appending this one …
      const next = takeBatch();
      if (next.length) {
        currentBatch = next;
        pendingScan = prepareChunk(next);
      } else {
        pendingScan = null;
      }

      // … then append this chunk strictly in page order (pdf-lib requires it).
      // Every page keeps a (downscaled) thumbnail so the grid shows all of
      // them; the PDF bytes always contained every page regardless.
      for (const item of scanned) {
        const preview = await appendPage(output, item.canvas, {
          pageMode: profile.pageMode,
          drawBorder: profile.drawBorder,
          jpegQuality: profile.jpegQuality,
          sourcePageSize: item.sourcePageSize,
        });
        pageImages.push(preview);
        panel.page(item.pageNumber);
        panel.done(`Page ${item.pageNumber} of ${pagesToScan} scanned`);
        panel.progress(item.pageNumber, pagesToScan);
        // Free the bitmap now that the page is embedded: full-size A4
        // canvases are the scan's biggest memory peak.
        item.canvas.width = 0;
        item.canvas.height = 0;
      }
      if (!pendingScan) break;
    }

    panel.beginStep("Building PDF\u2026");
    panel.title("Assembling PDF\u2026");
    const bytes = await saveOutputDocument(output);
    panel.finishStep("Done! PDF ready");
    panel.title("Scan complete");
    logger.info("on-device scan finished", { pages: pagesToScan, worker: workerSource });
    return { bytes, pageImages };
  } finally {
    // A scan started but never awaited (the append loop threw) must not raise
    // an unhandled rejection on its own.
    if (pendingScan) pendingScan.catch(() => {});
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
