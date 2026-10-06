/**
 * Session state for a scan session on one page.
 *
 * Scope is deliberately small: the results a page is currently showing plus
 * the object-URL lifecycle. Server state is never mirrored here (Convex-style
 * reactive state does not apply; the API is request/response).
 *
 * Why a module instead of page-local variables: the browser path creates and
 * revokes `blob:` URLs, and leaking them leaks whole PDFs. Keeping creation
 * and revocation in one place is what makes that safe.
 */

import { LIMITS } from "./constants.js";
import { logger } from "./logger.js";

const state = {
  /** @type {Array<{name: string, id?: string, width?: number, height?: number, error?: string}>} */
  scannedPages: [],
  /** @type {string|null} filename of the server-scanned PDF */
  scannedPdfName: null,
  /** @type {string|null} object URL of a locally built PDF */
  localPdfUrl: null,
  /** signature of the last processed file selection (dedupe guard) */
  lastSelectionSignature: "",
  /** true while a scan is running (blocks re-entrant uploads) */
  busy: false,
};

/** Read-only-ish accessor for the current session state. */
export function getState() {
  return state;
}

/**
 * Build the dedupe signature of a selection.
 *
 * @param {FileList|File[]} files
 * @returns {string}
 */
export function selectionSignature(files) {
  return Array.from(files || [])
    .map((f) => `${f.name}:${f.size}:${f.lastModified}`)
    .sort()
    .join("|");
}

/**
 * True when `files` is a genuinely new selection (the same drop twice in a row
 * is ignored so a double-fired `change` event cannot start two scans).
 *
 * @param {FileList|File[]} files
 * @returns {boolean}
 */
export function isNewSelection(files) {
  const signature = selectionSignature(files);
  if (!signature || signature === state.lastSelectionSignature) return false;
  state.lastSelectionSignature = signature;
  return true;
}

/** Forget the dedupe signature (used by "Scan more"). */
export function clearSelectionSignature() {
  state.lastSelectionSignature = "";
}

/**
 * Revoke and clear the current local PDF object URL.
 */
export function clearLocalPdfUrl() {
  if (state.localPdfUrl) {
    try {
      URL.revokeObjectURL(state.localPdfUrl);
    } catch (error) {
      logger.warn("could not revoke local PDF URL", error);
    }
    state.localPdfUrl = null;
  }
}

/**
 * Store the blob URL of a freshly built local PDF.
 *
 * @param {Blob} blob
 * @returns {string} the object URL
 */
export function setLocalPdfBlob(blob) {
  clearLocalPdfUrl();
  state.localPdfUrl = URL.createObjectURL(blob);
  return state.localPdfUrl;
}

/** Remove any local PDF object URL (see `clearLocalPdfUrl`). */
export function clearLocalPdf() {
  clearLocalPdfUrl();
}

/**
 * Reset everything a finished scan produced and return to the upload view.
 * Keeps `busy` untouched (the caller controls the pipeline).
 */
export function resetResults() {
  clearLocalPdfUrl();
  state.scannedPages = [];
  state.scannedPdfName = null;
  state.lastSelectionSignature = "";
}

/**
 * Should another page thumbnail be kept?
 *
 * @param {number} currentCount
 * @returns {boolean}
 */
export function canKeepThumbnail(currentCount) {
  return currentCount < LIMITS.maxThumbnails;
}

export const session = state;
