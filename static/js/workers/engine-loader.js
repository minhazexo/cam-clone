/**
 * Scan-engine loader: warms the OpenCV.js engine inside a WORKER thread.
 *
 * Why a worker and not a `<script>` tag: `opencv.js` is ~10 MB of WASM + glue,
 * and parsing it on the main thread freezes the page for seconds. Instead the
 * real scan worker is spawned with a `{ping}` probe and kept warm; the loader
 * hands that same worker to every scan (and grows a pool of extra warm workers
 * on demand for parallel scans), so the engine is parsed once per worker per
 * page load — never once per page scanned.
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
 * Extra warmed scan workers spawned on demand for parallel scans.
 * The first worker of a pool is always `warmWorker`; these are the rest.
 * @type {Worker[]}
 */
const spareWorkers = [];
/** In-flight spawn (serialises pool growth so callers cannot double-spawn). */
let spawning = null;

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
      warmWorker = worker;
      return { source: "v2-full", worker };
    } catch (error) {
      logger.warn("full scan engine unavailable, using light worker", error);
      const worker = await probe(ASSETS.scanWorkerFallback, false);
      warmWorker = worker;
      return { source: "fallback", worker };
    }
  })().catch((error) => {
    pending = null; // allow a later retry (e.g. after a transient load error)
    throw error;
  });
  return pending;
}

/** Warm one extra worker and append it to `spareWorkers` (never fails the scan). */
function spawnSpare() {
  if (!spawning) {
    spawning = probe(ASSETS.scanWorkerV2, true)
      .then((worker) => {
        spareWorkers.push(worker);
        return true;
      })
      .catch((error) => {
        logger.warn("extra scan worker failed to warm up; continuing with fewer", error);
        return false;
      })
      .finally(() => {
        spawning = null;
      });
  }
  return spawning;
}

/**
 * Ensure `size` scan workers are warm and return them as an array.
 *
 * Extra workers are spawned lazily — only when a scan actually has more than
 * one page to chew through — because compiling ~10 MB of WASM is not free and
 * a single-page PDF must not pay for it. They then stay warm for later scans,
 * exactly like the primary worker. Any worker that cannot warm up is dropped
 * silently: a smaller pool is always a valid outcome.
 *
 * @param {number} size number of workers the caller wants (>= 1)
 * @returns {Promise<{source: string, workers: Worker[]}>}
 */
async function ensurePool(size) {
  const primary = await ensure();
  const want = Math.max(1, Math.floor(size || 1));
  // The light fallback worker is a last resort: run it alone (legacy path).
  if (want > 1 && primary.source === "v2-full") {
    while (spareWorkers.length + 1 < want) {
      const warmed = await spawnSpare();
      if (!warmed) break;
    }
  }
  return {
    source: primary.source,
    workers: [primary.worker, ...spareWorkers.slice(0, want - 1)],
  };
}

/** The warm worker, if one has been created (null before warm-up). */
export function currentWorker() {
  return warmWorker;
}

/** Terminate the warm worker (called on `pagehide`). */
export function shutdownEngine() {
  const dispose = (worker) => {
    try {
      worker.terminate();
    } catch (error) {
      logger.debug("worker terminate failed", error);
    }
  };
  if (warmWorker) dispose(warmWorker);
  for (const worker of spareWorkers) dispose(worker);
  warmWorker = null;
  spareWorkers.length = 0;
  pending = null;
}

/**
 * Terminate workers and forget them, so the next acquire warms fresh ones.
 *
 * Used when a worker's WASM engine threw an uncaught C++ exception: the
 * module is left in an undefined state (the glue's `__exception_last` is
 * still set) and must not receive another page. Workers that are not in
 * the pool (per-scan fallback workers) are simply terminated.
 *
 * @param {Worker[]} workers
 */
function discard(workers) {
  for (const worker of workers || []) {
    if (!worker) continue;
    const index = spareWorkers.indexOf(worker);
    if (index >= 0) spareWorkers.splice(index, 1);
    if (worker === warmWorker) {
      // `ensure()` short-circuits on `pending`: it must re-probe instead of
      // handing back the terminated worker.
      warmWorker = null;
      pending = null;
    }
    try {
      worker.terminate();
    } catch (error) {
      logger.debug("worker terminate failed", error);
    }
  }
}

/** Public engine facade, including the legacy `window.RScanEngine` API. */
export const engine = {
  /** @returns {Promise<{source: string, worker: Worker}>} */
  acquire: ensure,
  /**
   * Warm up to `size` workers (1 = legacy single-worker behaviour).
   *
   * @param {number} size
   * @returns {Promise<{source: string, workers: Worker[]}>}
   */
  acquirePool: ensurePool,
  /** Terminate workers and drop them from the warm pool (see `discard`). */
  discard,
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
