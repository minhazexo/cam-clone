/**
 * Result card rendering and downloads.
 *
 * Three result shapes exist, matching the three ways a scan can finish:
 *
 *  - scanned images      -> one card per page with a preview and download link
 *                           (with a per-file error variant)
 *  - server PDF          -> one card with an elapsed-time caption
 *  - on-device PDF       -> one card with a preview (home page fallback) or a
 *                           per-page card grid (the /scan-pdf page)
 *
 * The markup (class names: `result-card`, `result-card-img`, …) is the
 * contract with `static/css/style.css`.
 */

import { clearChildren, createEl, downloadUrl, escapeHtml, safeFilename } from "../core/dom.js";
import { getState } from "../core/state.js";
import { ENDPOINTS } from "../core/constants.js";

/** URL of a scanned image artifact (`GET /api/image/<id>`). */
const imageUrl = (id) => ENDPOINTS.image(id);

/** URL of a scanned PDF artifact (`GET /api/pdf/<name>`). */
const pdfUrl = (name) => ENDPOINTS.pdf(name);

const DOWNLOAD_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
  '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>' +
  '<polyline points="7 10 12 15 17 10"/>' +
  '<line x1="12" y1="15" x2="12" y2="3"/></svg>';

const PDF_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">' +
  '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>' +
  '<polyline points="14 2 14 8 20 8"/>' +
  '<line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>';

/**
 * Render scanned image pages into `grid` (clearing it first).
 *
 * @param {HTMLElement|null} grid
 * @param {Array<{name: string, id?: string, width?: number, height?: number, error?: string}>} pages
 */
export function renderImageResults(grid, pages) {
  if (!grid) return;
  clearChildren(grid);

  pages.forEach((page) => {
    if (page.error) {
      const card = createEl("div", "result-card");
      card.innerHTML =
        '<div class="result-card-body">' +
        `<div class="result-card-name">${escapeHtml(page.name)}</div>` +
        `<div class="result-card-meta" style="color:#f87171">Error: ${escapeHtml(page.error)}</div>` +
        "</div>";
      grid.appendChild(card);
      return;
    }

    const card = createEl("div", "result-card");
    card.innerHTML =
      `<img class="result-card-img" src="${imageUrl(page.id)}" alt="${escapeHtml(page.name)}" loading="lazy">` +
      '<div class="result-card-body">' +
      `<div class="result-card-name">${escapeHtml(page.name)}</div>` +
      `<div class="result-card-meta">${page.width} \u00d7 ${page.height}px</div>` +
      '<div class="result-card-actions">' +
      `<a class="btn btn-primary btn-sm" href="${imageUrl(page.id)}" download="${safeFilename(page.name, "scanned_page")}">` +
      `${DOWNLOAD_ICON}Download</a></div></div>`;
    grid.appendChild(card);
  });
}

/**
 * Render the server-scanned PDF card.
 *
 * @param {HTMLElement|null} grid
 * @param {{originalName: string, pdfName: string, elapsed?: number}} result
 */
export function renderServerPdfResult(grid, result) {
  if (!grid) return;
  clearChildren(grid);

  const url = pdfUrl(result.pdfName);
  const elapsed = result.elapsed ? ` \u00b7 ${result.elapsed}s` : "";
  const card = createEl("div", "result-card");
  card.innerHTML =
    `<div class="result-card-pdf">${PDF_ICON}<p>Scanned PDF</p></div>` +
    '<div class="result-card-body">' +
    `<div class="result-card-name">${escapeHtml(result.originalName)}</div>` +
    `<div class="result-card-meta">Server scan complete${elapsed}</div>` +
    '<div class="result-card-actions">' +
    `<a class="btn btn-success btn-sm" href="${url}" download="${safeFilename(result.originalName, "scanned_document")}">` +
    `${DOWNLOAD_ICON}Download PDF</a></div></div>`;
  grid.appendChild(card);
}

/**
 * Render the on-device PDF card used by the home page fallback.
 *
 * @param {HTMLElement|null} grid
 * @param {{originalName: string, pageImages: Array<{dataUrl: string}>, blobUrl: string}} result
 */
export function renderLocalPdfResult(grid, result) {
  if (!grid || !result.pageImages.length) return;
  clearChildren(grid);

  const preview = result.pageImages[0];
  const card = createEl("div", "result-card");
  card.innerHTML =
    `<img class="result-card-img" src="${preview.dataUrl}" alt="Local scan preview">` +
    '<div class="result-card-body">' +
    `<div class="result-card-name">${escapeHtml(result.originalName)}</div>` +
    `<div class="result-card-meta">${result.pageImages.length} page(s) scanned locally</div>` +
    '<div class="result-card-actions">' +
    `<a class="btn btn-success btn-sm" href="${result.blobUrl}" download="${safeFilename(result.originalName, "scanned_document")}">` +
    `${DOWNLOAD_ICON}Download PDF</a></div></div>`;
  grid.appendChild(card);
}

/**
 * Render per-page cards for the on-device `/scan-pdf` page.
 *
 * @param {HTMLElement|null} grid
 * @param {string} originalName
 * @param {Array<{dataUrl: string, width: number, height: number}>} pageImages
 */
export function renderLocalPageGrid(grid, originalName, pageImages) {
  if (!grid) return;
  clearChildren(grid);

  pageImages.forEach((image, index) => {
    const card = createEl("div", "result-card");
    card.innerHTML =
      `<img class="result-card-img" src="${image.dataUrl}" alt="Scanned page ${index + 1}" loading="lazy">` +
      '<div class="result-card-body">' +
      `<div class="result-card-name">${escapeHtml(originalName)} \u2014 page ${index + 1}</div>` +
      `<div class="result-card-meta">${image.width} \u00d7 ${image.height}px</div>` +
      "</div>";
    grid.appendChild(card);
  });
}

/**
 * Wire the "Download All" button to a fresh handler (the on-device page points
 * it at the in-memory blob; the home page downloads every artifact).
 *
 * @param {HTMLElement|null} button
 * @param {() => void} handler
 */
export function setDownloadAllHandler(button, handler) {
  if (button) button.onclick = handler;
}

/**
 * Download every artifact produced by the current home-page scan: scanned
 * images, the server PDF (if any) and the local PDF (if any).
 *
 * @param {HTMLElement|null} button
 */
export function bindDownloadAll(button) {
  setDownloadAllHandler(button, downloadAllArtifacts);
}

/** Download all artifacts referenced by the current session state. */
export function downloadAllArtifacts() {
  const state = getState();

  state.scannedPages.forEach((page) => {
    if (page.id) downloadUrl(imageUrl(page.id), safeFilename(page.name, "scanned_page"));
  });
  if (state.scannedPdfName) {
    downloadUrl(pdfUrl(state.scannedPdfName), state.scannedPdfName);
  }
  if (state.localPdfUrl) {
    downloadUrl(state.localPdfUrl, "scanned_document.pdf");
  }
}
