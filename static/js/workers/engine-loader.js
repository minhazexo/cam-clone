/**
 * Scan-engine loader: warms the OpenCV.js engine inside a WORKER thread.
 *
 * Why a worker and not a `<script>` tag: `opencv.js` is ~10 MB of WASM + glue,
 * and parsing it on the main thread freezes the page for seconds. Instead the
 * real scan worker is spawned with a `{ping}` probe and kept warm; the loader
 * hands that same worker to every scan, so the engine is parsed once per page
 * load (never once per scan).
 *
 * Behaviour preserved from `static/js/opencv-loader.js`:
 *  - prefers the full pipeline worker (`scan-worker-v2.js`, answers `{ready:true}`);
 *  - falls back to the light worker (`scan-worker.js`) which has no ping
 *    handler, probed with a 4x4 dummy image instead;
 *  - reports `{source, worker}` to `window.RScanEngine.ready(onReady, onError)`
 *    so any legacy caller keeps working.
 *
 * The worker itself is documented in `docs/SCAN_PIPELINE.md` (worker protocol).
 */

import { ASSETS } from "../core/constants.js";
import { logger } from "../core/logger.js";

const PROBE_TIMEOUT_MS = 120000;

/** @type {Promise<{source: string, worker: Worker}>|null} */
let pending = null;
/** @type {Worker|null} */
let warmWorker = null;

/**
 * Spawn a worker and wait until it reports readiness.
 *
 * @param {string} url
 * @param {boolean} usePing send `{ping:true}` (v2) instead of a dummy image (v1)
 * @returns {Promise<Worker>} the warm worker, never terminated on success
 */
function probe(url, usePing) {
  return new Promise((resolve, reject) => {
    let worker;
    try {
      worker = new Worker(url);
    } catch (error) {
      reject(error);
      return;
    }

    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      try {
        worker.terminate();
      } catch (error) {
        logger.debug("worker terminate failed", error);
      }
      reject(new Error(`engine probe timeout: ${url}`));
    }, PROBE_TIMEOUT_MS);

    worker.onerror = () => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      try {
        worker.terminate();
      } catch (error) {
        logger.debug("worker terminate failed", error);
      }
      reject(new Error(`worker error: ${url}`));
    };

    worker.onmessage = (event) => {
      if (done) return;
      const data = event && event.data;
      const ok = usePing ? data && data.ready === true : data && data.pixels;
      if (!ok) return; // ignore unrelated messages
      done = true;
      clearTimeout(timer);
      warmWorker = worker;
      logger.info("scan engine ready", url, usePing ? "(v2-full)" : "(fallback)");
      resolve(worker);
    };

    try {
      if (usePing) {
        worker.postMessage({ ping: true });
      } else {
        // The v1 worker has no ping handler: send a 4x4 image instead.
        const pixels = new Uint8ClampedArray(4 * 4 * 4);
        for (let i = 0; i < pixels.length; i += 1) pixels[i] = 240;
        worker.postMessage(
          { width: 4, height: 4, pixels: pixels.buffer },
          [pixels.buffer],
        );
      }
    } catch (error) {
      if (!done) {
        done = true;
        clearTimeout(timer);
        try {
          worker.terminate();
        } catch (innerError) {
          logger.debug("worker terminate failed", innerError);
        }
        reject(error);
      }
    }
  });
}

/**
 * Ensure the engine is warm (idempotent: one probe per page load).
 *
 * @returns {Promise<{source: string, worker: Worker}>}
 */
function ensure() {
  if (pending) return pending;
  pending = (async () => {
    try {
      const worker = await probe(ASSETS.scanWorkerV2, true);
      return { source: "v2-full", worker };
    } catch (error) {
      logger.warn("full scan engine unavailable, using light worker", error);
      const worker = await probe(ASSETS.scanWorkerFallback, false);
      return { source: "fallback", worker };
    }
  })().catch((error) => {
    pending = null; // allow a later retry (e.g. after a transient load error)
    throw error;
  });
  return pending;
}

/** The warm worker, if one has been created (null before warm-up). */
export function currentWorker() {
  return warmWorker;
}

/** Terminate the warm worker (called on `pagehide`). */
export function shutdownEngine() {
  if (!warmWorker) return;
  try {
    warmWorker.terminate();
  } catch (error) {
    logger.debug("worker terminate failed", error);
  }
  warmWorker = null;
  pending = null;
}

/** Public engine facade, including the legacy `window.RScanEngine` API. */
export const engine = {
  /** @returns {Promise<{source: string, worker: Worker}>} */
  acquire: ensure,
  /**
   * Legacy callback API: `RScanEngine.ready(onReady, onError)`.
   *
   * @param {(info: {source: string, worker: Worker}) => void} [onReady]
   * @param {(error: Error) => void} [onError]
   */
  ready(onReady, onError) {
    ensure().then(
      (info) => {
        if (onReady) onReady(info);
      },
      (error) => {
        if (onError) onError(error);
      },
    );
  },
};

// Keep the historical global so any older inline snippet keeps working.
if (typeof window !== "undefined") {
  window.RScanEngine = engine;
}
