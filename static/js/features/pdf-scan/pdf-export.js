/**
 * Scanned PDF assembly (pdf-lib) — the on-device counterpart of
 * `rscan/pdf/assembler.py`.
 *
 * Two page modes are supported, mirroring the server options:
 *
 *  - `a4`     : uniform A4 pages, orientation matched to the image, image
 *               aspect-fit and centred (full-bleed, no white bands);
 *  - `source` : legacy page-per-image at the PDF's own page size.
 */

import { A4_PAGE, PAGE_BORDER_STROKE_RATIO } from "../../core/constants.js";
import { ensurePdfEngine } from "./pdf-engine.js";
import { canvasToJpegBytes, canvasToDataUrl, drawPageBorder } from "./pdf-renderer.js";

/**
 * Create an empty output document.
 *
 * @returns {Promise<object>} pdf-lib PDFDocument
 */
export async function createOutputDocument() {
  const { PDFLib } = await ensurePdfEngine();
  return PDFLib.PDFDocument.create();
}

/**
 * Append one scanned page to the output document.
 *
 * @param {object} output pdf-lib document
 * @param {HTMLCanvasElement} canvas scanned page (already enhanced)
 * @param {{pageMode: string, drawBorder: boolean, jpegQuality: number,
 *          sourcePageSize?: {width: number, height: number}}} options
 * @returns {Promise<{dataUrl: string, width: number, height: number}>} preview info
 */
export async function appendPage(output, canvas, options) {
  if (options.drawBorder) drawPageBorder(canvas, PAGE_BORDER_STROKE_RATIO);

  const jpegBytes = canvasToJpegBytes(canvas, options.jpegQuality);
  const embedded = await output.embedJpg(jpegBytes);

  let pageSize;
  if (options.pageMode === "a4") {
    const landscape = canvas.width >= canvas.height;
    pageSize = landscape ? A4_PAGE.landscape : A4_PAGE.portrait;
  } else {
    const size = options.sourcePageSize || { width: canvas.width, height: canvas.height };
    pageSize = [size.width, size.height];
  }

  const [pageWidth, pageHeight] = pageSize;
  const pdfPage = output.addPage(pageSize);
  const fit = Math.min(pageWidth / canvas.width, pageHeight / canvas.height);
  pdfPage.drawImage(embedded, {
    x: (pageWidth - canvas.width * fit) / 2,
    y: (pageHeight - canvas.height * fit) / 2,
    width: canvas.width * fit,
    height: canvas.height * fit,
  });

  return {
    dataUrl: canvasToDataUrl(canvas, options.jpegQuality),
    width: canvas.width,
    height: canvas.height,
  };
}

/**
 * Serialise the output document.
 *
 * @param {object} output pdf-lib document
 * @returns {Promise<Uint8Array>}
 */
export function saveOutputDocument(output) {
  return output.save();
}
