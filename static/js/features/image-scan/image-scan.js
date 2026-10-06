/**
 * Image scan feature: files -> scanned pages on the server.
 *
 * The heavy lifting is the API call; this module owns the user-facing steps
 * (progress panel narration, error notification) so the home page entrypoint
 * stays declarative.
 */

import { scanImages } from "../../api/scan-api.js";
import { toUserMessage } from "../../core/errors.js";
import { getState } from "../../core/state.js";
import { notifyError } from "../../ui/notifications.js";

/**
 * @typedef {import('../pdf-scan/on-device-pdf-scan.js').ScanPanel} ScanPanel
 */

/**
 * Scan the given images and store the results in session state.
 *
 * @param {File[]|FileList} files
 * @param {ScanPanel} panel
 * @returns {Promise<Array<{name: string, id?: string, width?: number, height?: number, error?: string}>>}
 * @throws {Error} when the request fails or returns no pages
 */
export async function scanImageFiles(files, panel) {
  const fileArray = Array.from(files);
  panel.beginStep(`Scanning ${fileArray.length} image(s)\u2026`);
  panel.title("Scanning images\u2026");

  let pages;
  try {
    pages = await scanImages(fileArray);
  } catch (error) {
    notifyError(`Scan failed: ${toUserMessage(error)}`);
    throw error;
  }

  if (!pages.length) {
    const error = new Error("No pages were scanned.");
    notifyError(error.message);
    throw error;
  }

  panel.finishStep();
  getState().scannedPages = pages;
  return pages;
}
