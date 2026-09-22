/* RScan scan-engine loader: warms the OpenCV engine inside a WORKER thread.
 * The 10MB opencv.js must never parse on the main thread (it freezes the
 * page for seconds) — so instead of a <script> tag, this spawns the real
 * scan worker with a {ping} probe and reports readiness. Same public API:
 * window.RScanEngine.ready(onReady, onError) with {source, worker}.
 */
(function () {
  "use strict";

  var V2_URL = "/static/js/scan-worker-v2.js";
  var FALLBACK_URL = "/static/js/scan-worker.js";
  var PROBE_TIMEOUT_MS = 120000;

  var pending = null;

  function probe(url, usePing) {
    return new Promise(function (resolve, reject) {
      var worker;
      try {
        worker = new Worker(url);
      } catch (err) {
        reject(err);
        return;
      }
      var done = false;
      var timer = setTimeout(function () {
        if (done) return;
        done = true;
        try { worker.terminate(); } catch (e) { /* ignore */ }
        reject(new Error("engine probe timeout: " + url));
      }, PROBE_TIMEOUT_MS);
      worker.onerror = function () {
        if (done) return;
        done = true;
        clearTimeout(timer);
        try { worker.terminate(); } catch (e) { /* ignore */ }
        reject(new Error("worker error: " + url));
      };
      worker.onmessage = function (e) {
        if (done) return;
        var data = e && e.data;
        var ok = usePing ? (data && data.ready === true)
                         : (data && data.pixels);
        if (!ok) return; // ignore unrelated messages
        done = true;
        clearTimeout(timer);
        resolve(worker); // hand the WARM worker to the caller — no re-parse
      };
      try {
        if (usePing) {
          worker.postMessage({ ping: true });
        } else {
          // v1 fallback has no ping handler: send a 4x4 image instead.
          var px = new Uint8ClampedArray(4 * 4 * 4);
          for (var i = 0; i < px.length; i++) px[i] = 240;
          worker.postMessage(
            { width: 4, height: 4, pixels: px.buffer }, [px.buffer]);
        }
      } catch (err) {
        if (!done) {
          done = true;
          clearTimeout(timer);
          try { worker.terminate(); } catch (e2) { /* ignore */ }
          reject(err);
        }
      }
    });
  }

  function ensure() {
    if (pending) return pending;
    pending = (async function () {
      try {
        var worker = await probe(V2_URL, true);
        return { source: "v2-full", worker: worker };
      } catch (err) {
        var fallback = await probe(FALLBACK_URL, false);
        return { source: "fallback", worker: fallback };
      }
    })().catch(function (err) {
      pending = null;
      throw err;
    });
    return pending;
  }

  window.RScanEngine = {
    ready: function (onReady, onError) {
      ensure().then(
        function (info) { if (onReady) onReady(info); },
        function (err) { if (onError) onError(err); }
      );
    }
  };
})();
