/**
 * Server PDF scan: upload -> background job -> SSE progress -> result.
 *
 * This is the flow behind "drop a PDF on the home page". It is two phases:
 *
 *   1. upload the file and get a `job_id` (progress panel shows the upload);
 *   2. subscribe to the job's SSE stream and mirror its events into the panel.
 *
 * On any failure the caller falls back to the on-device pipeline
 * (`on-device-pdf-scan.js`), which is why this module deliberately never
 * notifies the user itself — it just throws.
 */

import { checkServerHealth } from "../../api/health-api.js";
import { startPdfScan } from "../../api/pdf-api.js";
import { formatBytes } from "../../core/dom.js";
import { logger } from "../../core/logger.js";
import { followServerProgress } from "./pdf-progress.js";

/**
 * @typedef {import('./on-device-pdf-scan.js').ScanPanel} ScanPanel
 */

/**
 * Scan a PDF on the server.
 *
 * @param {File} file
 * @param {number|null} pageLimit null means "all pages"
 * @param {ScanPanel} panel
 * @returns {Promise<{originalName: string, pdfName: string, elapsed: number}>}
 */
export async function runServerPdfScan(file, pageLimit, panel) {
  panel.title("Uploading your PDF\u2026");
  panel.scanLine(true);
  panel.beginStep(`Uploading "${file.name}" (${formatBytes(file.size)})\u2026`);

  let jobId;
  try {
    jobId = await startPdfScan(file, pageLimit);
  } catch (error) {
    panel.scanLine(false);
    await reportDiagnostics(error);
    throw error;
  }

  panel.finishStep("PDF uploaded successfully");
  panel.title("Scanning your document\u2026");

  const result = await followServerProgress(jobId, panel);
  return { originalName: file.name, pdfName: result.pdfName, elapsed: result.elapsed };
}

/**
 * Log why the server flow failed (health probe is diagnostic only — it never
 * changes what the user sees, the caller decides that).
 *
 * @param {unknown} error
 */
async function reportDiagnostics(error) {
  const healthy = await checkServerHealth();
  logger.warn("server PDF scan failed", {
    reachable: healthy,
    reason: error && error.message ? error.message : String(error),
  });
}
