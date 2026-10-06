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
 * Get the worker to use for a scan profile.
 *
 * @param {object} profile one of `PDF_PROFILES`
 * @returns {Promise<{worker: Worker, source: string}>}
 */
export async function acquireWorker(profile) {
  if (profile.useEngineLoader) {
    const info = await engine.acquire();
    return { worker: info.worker, source: info.source };
  }
  // Fallback profile: a throwaway light worker, exactly as the legacy path did.
  logger.debug("creating fallback scan worker", ASSETS.scanWorkerFallback);
  return { worker: new Worker(ASSETS.scanWorkerFallback), source: "fallback" };
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
        reject(new EngineUnavailableError(`Scan worker failed: ${data.error}`));
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
      reject(new EngineUnavailableError("Scan worker stopped unexpectedly."));
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
 * Terminate a worker that this module created (never the warm engine worker).
 *
 * @param {Worker|null} worker
 * @param {{keepAlive?: boolean}} [options]
 */
export function releaseWorker(worker, options = {}) {
  if (!worker || options.keepAlive) return;
  try {
    worker.terminate();
  } catch (error) {
    logger.debug("worker terminate failed", error);
  }
}

/** Warm up the full engine (used by the /scan-pdf page before enabling the button). */
export function warmUpEngine(onReady, onError) {
  return engine.ready(onReady, onError);
}
