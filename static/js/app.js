/**
 * Home page entrypoint (`/`).
 *
 * Composition root only: it binds the DOM, decides which flow a dropped file
 * belongs to, and delegates everything else to `core/`, `ui/` and
 * `features/`. No scan, PDF or rendering logic lives here.
 *
 * Flows:
 *   images -> POST /api/scan                     -> image result cards
 *   PDF    -> server job + SSE progress          -> server PDF result card
 *             on failure: on-device fallback     -> local PDF result card
 *
 * Flow details live in:
 *   features/image-scan/   image upload + scanning
 *   features/pdf-scan/     server SSE flow, on-device pipeline, result export
 */

import { ACCEPT, LIMITS, PDF_PROFILES } from "./core/constants.js";
import { $, onReady } from "./core/dom.js";
import { logger, setDebug } from "./core/logger.js";
import { getState, isNewSelection, resetResults, setLocalPdfBlob } from "./core/state.js";
import { scanImageFiles } from "./features/image-scan/image-scan.js";
import { runOnDevicePdfScan } from "./features/pdf-scan/on-device-pdf-scan.js";
import { runServerPdfScan } from "./features/pdf-scan/server-pdf-scan.js";
import { askPageLimit } from "./ui/modal.js";
import { notifyError } from "./ui/notifications.js";
import { createProcessingPanel } from "./ui/progress.js";
import { bindFilePickerButton, bindUploadZone } from "./ui/upload-zone.js";
import {
  bindDownloadAll,
  renderImageResults,
  renderLocalPdfResult,
  renderServerPdfResult,
} from "./ui/results.js";
import {
  clearResultsGrid,
  resultsGrid,
  showProcessingView,
  showResultsView,
  showUploadView,
} from "./ui/sections.js";

/** Delay before revealing a finished result (keeps the "done" step readable). */
const RESULT_REVEAL_DELAY_MS = { server: 600, local: 500 };

const panel = createProcessingPanel();

onReady(init);

function init() {
  setDebug(new URLSearchParams(window.location.search).has("debug"));

  const fileInput = $("fileInput");

  bindUploadZone({
    zone: $("uploadZone"),
    input: fileInput,
    accept: ACCEPT.all,
    multiple: true,
    onFiles: handleFiles,
  });

  // "Scan Images" narrows the picker to images; the zone itself accepts PDFs.
  bindFilePickerButton({
    button: $("btnImages"),
    input: fileInput,
    accept: ACCEPT.images,
    multiple: true,
  });

  // "Scan PDF" is an <a href="/scan-pdf"> (on-device page): nothing to bind.
  bindDownloadAll($("btnDownloadAll"));

  const scanMore = $("btnScanMore");
  if (scanMore) scanMore.addEventListener("click", resetToUpload);

  logger.debug("home page ready");
}

/**
 * Entry point for a new file selection (drop or picker).
 *
 * @param {FileList|File[]} files
 */
async function handleFiles(files) {
  if (!files || !files.length) return;

  const state = getState();
  if (state.busy) return;
  if (!isNewSelection(files)) return;

  const fileArray = Array.from(files);
  const first = fileArray[0];
  const isPdf = first.type === "application/pdf" || /\.pdf$/i.test(first.name);

  state.busy = true;
  showProcessingView();
  panel.reset();

  try {
    if (isPdf) {
      await handlePdfSelection(fileArray, first);
    } else {
      await handleImageSelection(fileArray);
    }
  } finally {
    state.busy = false;
  }
}

/**
 * Image batch -> server scan -> image result cards.
 *
 * @param {File[]} fileArray
 */
async function handleImageSelection(fileArray) {
  try {
    const pages = await scanImageFiles(fileArray, panel);
    clearResultsGrid();
    renderImageResults(resultsGrid(), pages);
    showResultsView();
  } catch (error) {
    logger.warn("image scan failed", error);
    showUploadView();
  }
}

/**
 * PDF -> server job with live progress, falling back to the on-device pipeline.
 *
 * @param {File[]} fileArray
 * @param {File} file
 */
async function handlePdfSelection(fileArray, file) {
  if (fileArray.length !== 1) {
    notifyError("Please select one PDF at a time.");
    showUploadView();
    return;
  }

  let pageLimit;
  try {
    pageLimit = await askPageLimit();
  } catch (error) {
    // User cancelled the page-limit modal: back to upload, no error shown.
    showUploadView();
    return;
  }

  try {
    const result = await runServerPdfScan(file, pageLimit, panel);
    getState().scannedPdfName = result.pdfName;
    setTimeout(() => {
      clearResultsGrid();
      renderServerPdfResult(resultsGrid(), result);
      showResultsView();
    }, RESULT_REVEAL_DELAY_MS.server);
    return;
  } catch (error) {
    logger.warn("server PDF scan failed, using the on-device pipeline", error);
  }

  // Last-resort path: identical to the previous local fallback (all pages,
  // light worker, page-sized output) but now reached through the shared
  // on-device pipeline.
  panel.reset();
  try {
    const { bytes, pageImages } = await runOnDevicePdfScan(
      file, LIMITS.defaultPageLimit, panel, PDF_PROFILES.fallback);
    const blobUrl = setLocalPdfBlob(new Blob([bytes], { type: "application/pdf" }));
    setTimeout(() => {
      clearResultsGrid();
      renderLocalPdfResult(resultsGrid(), {
        originalName: file.name,
        pageImages,
        blobUrl,
      });
      showResultsView();
    }, RESULT_REVEAL_DELAY_MS.local);
  } catch (error) {
    logger.error("on-device fallback failed", error);
    notifyError(`Scan failed: ${error && error.message ? error.message : String(error)}`);
    showUploadView();
  }
}

/** "Scan more": drop all results and go back to the upload view. */
function resetToUpload() {
  if (getState().busy) return;
  resetResults();
  clearResultsGrid();
  panel.reset();
  showUploadView();
}
