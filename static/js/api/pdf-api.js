/**
 * Server PDF scan API client.
 *
 * Two-step job flow::

 *   1. `startPdfScan(file, pageLimit)` -> `{job_id}`   (POST /api/scan-pdf-start)
 *   2. `streamPdfProgress(jobId, handlers)`            (GET  /api/scan-pdf-progress/<id>, SSE)
 *
 * `scanPdfOnce` is the legacy single-shot endpoint (POST /api/scan-pdf); it is
 * kept because the endpoint still exists and is documented as the sync
 * alternative to the job flow.
 */

import { ENDPOINTS } from "../core/constants.js";
import { ProgressStreamError } from "../core/errors.js";
import { logger } from "../core/logger.js";
import { postForm } from "./client.js";

/**
 * Upload a PDF and start a background scan job.
 *
 * @param {File} file
 * @param {number|null} pageLimit null means "all pages"
 * @returns {Promise<string>} job id
 */
export async function startPdfScan(file, pageLimit) {
  const formData = new FormData();
  formData.append("file", file, file.name);
  if (Number.isInteger(pageLimit) && pageLimit >= 1) {
    formData.append("page_limit", String(pageLimit));
  }
  const payload = await postForm(ENDPOINTS.scanPdfStart, formData);
  if (!payload.job_id) throw new ProgressStreamError("Scan server did not return a job id.");
  return payload.job_id;
}

/**
 * Scan a PDF synchronously (legacy endpoint) and return the result filename.
 *
 * @param {File} file
 * @param {number|null} [pageLimit]
 * @returns {Promise<string>}
 */
export async function scanPdfOnce(file, pageLimit) {
  const formData = new FormData();
  formData.append("file", file, file.name);
  if (Number.isInteger(pageLimit) && pageLimit >= 1) {
    formData.append("page_limit", String(pageLimit));
  }
  const payload = await postForm(ENDPOINTS.scanPdf, formData);
  return payload.pdf;
}

/**
 * Subscribe to a job's progress events.
 *
 * @param {string} jobId
 * @param {{
 *   onEvent: (event: object) => void,
 *   onDone: (event: object) => void,
 *   onError: (error: Error) => void,
 * }} handlers
 * @returns {{close: () => void}} handle so the caller can abort the stream
 */
export function streamPdfProgress(jobId, handlers) {
  let source = new EventSource(ENDPOINTS.scanPdfProgress(jobId));
  let settled = false;

  const close = () => {
    if (!source) return;
    try {
      source.close();
    } catch (error) {
      logger.debug("EventSource close failed", error);
    }
    source = null;
  };

  source.onmessage = (message) => {
    let event;
    try {
      event = JSON.parse(message.data);
    } catch (error) {
      logger.warn("ignoring malformed progress event", message.data);
      return;
    }

    handlers.onEvent(event);

    if (event.type === "done") {
      settled = true;
      close();
      handlers.onDone(event);
    } else if (event.type === "error") {
      settled = true;
      close();
      handlers.onError(new ProgressStreamError(event.message || "Scan failed"));
    } else if (event.type === "_eof") {
      settled = true;
      close();
      handlers.onError(new ProgressStreamError("The scan ended unexpectedly."));
    }
  };

  source.onerror = () => {
    if (settled) return;
    settled = true;
    close();
    handlers.onError(new ProgressStreamError());
  };

  return { close };
}

/** URL of a scanned PDF artifact. */
export function pdfUrl(name) {
  return ENDPOINTS.pdf(name);
}
