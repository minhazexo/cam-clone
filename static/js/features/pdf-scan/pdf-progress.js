/**
 * Server PDF progress: translate SSE events into panel updates.
 *
 * The event vocabulary is defined by `rscan/jobs/events.py`; this module is the
 * single place that knows how each event looks to the user, so
 * `server-pdf-scan.js` stays a sequence of steps.
 *
 * Event -> UI mapping:
 *
 *   loading    "Loading PDF pages…"        step "Detecting pages in the PDF…"
 *   detected   "Scanning N pages…"         step done, counter + bar revealed
 *   scanning   "Scanning page n of N…"     current page + bar (n-1)/N
 *   page_done  "Page n scanned"            bar n/N
 *   assembling "Assembling scanned PDF…"   scan-line animation off
 *   done       "Scan complete!"            resolves with {pdf, elapsed}
 *   error      —                           rejects with the server message
 *   _eof       —                           stream-close sentinel (no UI)
 */

import { streamPdfProgress } from "../../api/pdf-api.js";
import { ProgressStreamError } from "../../core/errors.js";
import { logger } from "../../core/logger.js";

/**
 * @typedef {import('./on-device-pdf-scan.js').ScanPanel} ScanPanel
 */

/**
 * Follow a job until it finishes.
 *
 * @param {string} jobId
 * @param {ScanPanel} panel
 * @returns {Promise<{pdfName: string, elapsed: number}>}
 */
export function followServerProgress(jobId, panel) {
  return new Promise((resolve, reject) => {
    streamPdfProgress(jobId, {
      onEvent(event) {
        applyEvent(event, panel);
      },
      onDone(event) {
        resolve({ pdfName: event.pdf, elapsed: event.elapsed });
      },
      onError(error) {
        panel.scanLine(false);
        reject(error instanceof Error ? error : new ProgressStreamError(String(error)));
      },
    });
  });
}

/**
 * Apply one progress event to the panel.
 *
 * @param {object} event
 * @param {ScanPanel} panel
 */
export function applyEvent(event, panel) {
  switch (event.type) {
    case "loading":
      panel.title("Loading PDF pages\u2026");
      panel.beginStep("Detecting pages in the PDF\u2026");
      break;

    case "detected":
      panel.finishStep(
        `Found ${event.total} page${event.total === 1 ? "" : "s"} in the PDF`);
      panel.title(`Scanning ${event.total} page${event.total === 1 ? "" : "s"}\u2026`);
      panel.showTotal(event.total);
      break;

    case "scanning":
      panel.title(`Scanning page ${event.page} of ${event.total}\u2026`);
      panel.page(event.page);
      panel.beginStep(`Scanning page ${event.page} of ${event.total}\u2026`);
      panel.progress(event.page - 1, event.total);
      break;

    case "page_done":
      panel.finishStep(`Page ${event.page} scanned`);
      panel.page(event.page);
      panel.progress(event.page, event.total);
      break;

    case "assembling":
      panel.title("Assembling scanned PDF\u2026");
      panel.beginStep("Assembling all pages into final PDF\u2026");
      panel.scanLine(false);
      break;

    case "done":
      panel.finishStep(`Done! ${event.elapsed}s \u2014 PDF is ready`);
      panel.title("Scan complete!");
      panel.progress(1, 1);
      break;

    case "error":
      panel.scanLine(false);
      break;

    default:
      logger.debug("ignoring unknown progress event", event);
      break;
  }
}
