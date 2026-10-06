/**
 * Scan worker client — the browser side of the worker protocol.
 *
 * Protocol (documented in `docs/SCAN_PIPELINE.md` and implemented in
 * `static/js/workers/scan-worker-v2.js`):
 *
 *   request   { width, height, pixels: ArrayBuffer }        RGBA, transferable
 *   response  { width, height, pixels: ArrayBuffer, stats } RGBA, transferable
 *   error     { error: string }
 *   warmup    { ping: true } -> { ready: true, engine: "v2-full" }
 *
 * The pixel buffer is transferred (zero-copy): after `postMessage` the
 * caller's ArrayBuffer is detached, which is why the canvas is the only owner
 * of the pixels. Mat cleanup happens inside the worker; nothing is shared
 * across pages.
 */

import { ASSETS } from "../../core/constants.js";
import { EngineUnavailableError } from "../../core/errors.js";
import { logger } from "../../core/logger.js";
import { engine } from "../../workers/engine-loader.js";

/**
 * Get the scan workers to use for a scan profile.
 *
 * Pool policy lives in `core/constants.js` (`scanPoolPlan`): 1 worker keeps
 * the legacy single-worker behaviour, N workers scan N pages at once.
 *
 * @param {object} profile one of `PDF_PROFILES`
 * @param {number} [size] how many workers the caller wants (>= 1)
 * @returns {Promise<{workers: Worker[], source: string}>}
 */
export async function acquireWorkers(profile, size = 1) {
  if (profile.useEngineLoader) {
    const info = await engine.acquirePool(size);
    return { workers: info.workers, source: info.source };
  }
  // Fallback profile: a throwaway light worker, exactly as the legacy path did.
  logger.debug("creating fallback scan worker", ASSETS.scanWorkerFallback);
  return { workers: [new Worker(ASSETS.scanWorkerFallback)], source: "fallback" };
}

/**
 * Split page numbers into ordered chunks of at most `size` pages.
 *
 * Chunking is what keeps parallel scanning safe: a chunk is scanned by the
 * pool one worker per page, then appended to the PDF in document order, so
 * pages never finish out of order and only `size` canvases are alive at once.
 *
 * @param {number} total number of pages to scan
 * @param {number} size workers available (chunk size)
 * @returns {number[][]} 1-based page numbers, in document order
 */
export function planPageChunks(total, size) {
  const perChunk = Math.max(1, Math.floor(size || 1));
  const chunks = [];
  for (let start = 1; start <= total; start += perChunk) {
    const chunk = [];
    for (let page = start; page <= total && chunk.length < perChunk; page += 1) {
      chunk.push(page);
    }
    chunks.push(chunk);
  }
  return chunks;
}

/**
 * Enhance one canvas in place through the worker.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {Worker} worker
 * @returns {Promise<HTMLCanvasElement>} the same canvas, with scanned pixels
 */
export function enhanceCanvas(canvas, worker) {
  return new Promise((resolve, reject) => {
    const context = canvas.getContext("2d", { willReadFrequently: true });
    let imageData;
    try {
      imageData = context.getImageData(0, 0, canvas.width, canvas.height);
    } catch (error) {
      reject(error);
      return;
    }

    worker.onmessage = (event) => {
      const data = event && event.data;
      if (data && data.error) {
        // A bare numeric detail is a raw C++ exception pointer from the
        // Emscripten glue (`throw ptr`): an uncaught OpenCV assertion or an
        // out-of-memory inside the worker's WASM heap. The module is left in
        // an undefined state, so callers must treat the worker as poisoned
        // (see `engineFault`) and replace it before sending another page.
        const raw = String(data.error);
        const detail = /^-?\d+$/.test(raw)
          ? "the scan engine hit an OpenCV error or ran out of memory"
          : raw;
        logger.warn("scan worker engine fault", { code: raw });
        const error = new EngineUnavailableError(`Scan worker failed: ${detail}`);
        error.engineFault = true;
        reject(error);
        return;
      }
      if (!data || !data.pixels) {
        reject(new EngineUnavailableError("Worker returned invalid data."));
        return;
      }
      try {
        context.putImageData(
          new ImageData(new Uint8ClampedArray(data.pixels), data.width, data.height),
          0,
          0,
        );
      } catch (error) {
        reject(error);
        return;
      }
      resolve(canvas);
    };

    worker.onerror = () => {
      const error = new EngineUnavailableError("Scan worker stopped unexpectedly.");
      error.engineFault = true;
      reject(error);
    };

    try {
      worker.postMessage(
        { width: canvas.width, height: canvas.height, pixels: imageData.data.buffer },
        [imageData.data.buffer],
      );
    } catch (error) {
      reject(error);
    }
  });
}

/**
 * Terminate a worker, or hand it back to the pool.
 *
 * @param {Worker|null} worker
 * @param {{keepAlive?: boolean, discard?: boolean}} [options]
 *   `keepAlive` leaves a warm pool worker untouched; `discard` terminates
 *   the worker AND drops it from the warm pool (used for engine faults,
 *   whose WASM module must never receive another page).
 */
export function releaseWorker(worker, options = {}) {
  if (!worker) return;
  if (options.discard) {
    engine.discard([worker]);
    return;
  }
  if (options.keepAlive) return;
  try {
    worker.terminate();
  } catch (error) {
    logger.debug("worker terminate failed", error);
  }
}

/**
 * Release every worker a scan acquired.
 *
 * The pool's engine workers stay warm (`keepAlive`) so the next scan reuses
 * them; a per-scan fallback worker is disposable.
 *
 * @param {Worker[]} workers
 * @param {{keepAlive?: boolean}} [options]
 */
export function releaseWorkers(workers, options = {}) {
  for (const worker of workers || []) releaseWorker(worker, options);
}

/** Warm up the full engine (used by the /scan-pdf page before enabling the button). */
export function warmUpEngine(onReady, onError) {
  return engine.ready(onReady, onError);
}
