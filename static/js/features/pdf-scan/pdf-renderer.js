/**
 * PDF page -> canvas rendering.
 *
 * Resolution is profile-driven (see `core/constants.js`):
 *
 *  - `full`     : 200 DPI (200/72 scale) for server parity, width-capped so a
 *                 large page cannot blow up memory on phones;
 *  - `fallback` : the legacy 2x cap used by the home page's last-resort path.
 */

import { PDF_PROFILES } from "../../core/constants.js";

/** Is the viewport a small screen (phones), where the render cap is lower? */
export function isSmallScreen() {
  const byWindow = window.innerWidth && window.innerWidth < 768;
  const byScreen = window.screen && window.screen.width && window.screen.width < 768;
  return Boolean(byWindow || byScreen);
}

/**
 * Compute the pdf.js render scale for a page under a profile.
 *
 * @param {{width: number}} pageSize page size in CSS pixels at scale 1
 * @param {object} profile one of `PDF_PROFILES`
 * @returns {number}
 */
export function renderScaleFor(pageSize, profile) {
  if (profile.renderDpi) {
    const capWidth = isSmallScreen() ? profile.capWidthSmall : profile.capWidthLarge;
    return Math.min(profile.renderDpi / 72, capWidth / pageSize.width);
  }
  return Math.min(profile.fallbackScaleCap, profile.fallbackFitWidth / pageSize.width);
}

/**
 * Render one pdf.js page into a fresh canvas.
 *
 * @param {object} pdfPage pdf.js page proxy
 * @param {object} [profile] scan profile (defaults to the full profile)
 * @returns {Promise<HTMLCanvasElement>} the rendered canvas (never tainted
 *          locally — the PDF bytes come from the user's own file)
 */
export async function renderPageToCanvas(pdfPage, profile = PDF_PROFILES.full) {
  const pageSize = pdfPage.getViewport({ scale: 1 });
  const viewport = pdfPage.getViewport({ scale: renderScaleFor(pageSize, profile) });
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(viewport.width));
  canvas.height = Math.max(1, Math.round(viewport.height));

  const context = canvas.getContext("2d");
  await pdfPage.render({ canvasContext: context, viewport }).promise;
  return canvas;
}

/**
 * Draw the black page frame used on uniform output pages.
 *
 * Mirrors `rscan/pdf/assembler.py:draw_page_border` (thickness ~0.3% of the
 * short side, inset by one stroke) so server and on-device output match.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {number} strokeRatio fraction of the short side
 */
export function drawPageBorder(canvas, strokeRatio) {
  const context = canvas.getContext("2d");
  if (!context) return;
  const lineWidth = Math.max(2, Math.round(Math.min(canvas.width, canvas.height) * strokeRatio));
  context.save();
  context.strokeStyle = "#000000";
  context.lineWidth = lineWidth;
  context.strokeRect(lineWidth, lineWidth, canvas.width - lineWidth * 2, canvas.height - lineWidth * 2);
  context.restore();
}

/** Canvas -> JPEG bytes. */
export function canvasToJpegBytes(canvas, quality) {
  const dataUrl = canvas.toDataURL("image/jpeg", quality);
  const binary = atob(dataUrl.split(",")[1]);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** Canvas -> data URL (used for result previews). */
export function canvasToDataUrl(canvas, quality) {
  return canvas.toDataURL("image/jpeg", quality);
}
