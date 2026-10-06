/**
 * On-device PDF scan page entrypoint (`/scan-pdf`).
 *
 * Everything here happens in the browser: `pdf.js` renders pages, the OpenCV
 * worker enhances them, `pdf-lib` assembles a uniform A4 PDF. Nothing is
 * uploaded, so the backend's size/time limits do not apply (only the local
 * 250 MB / 250 page caps from `core/constants.js`).
 *
 * Composition root only — the pipeline lives in
 * `features/pdf-scan/on-device-pdf-scan.js`.
 */

import { ACCEPT, PDF_PROFILES } from "./core/constants.js";
import { $, downloadUrl, onReady, safeFilename } from "./core/dom.js";
import { logger, setDebug } from "./core/logger.js";
import { getState, resetResults, setLocalPdfBlob } from "./core/state.js";
import { assertLocalScanAvailable, runOnDevicePdfScan } from "./features/pdf-scan/on-device-pdf-scan.js";
import { askPageLimit } from "./ui/modal.js";
import { createProcessingPanel } from "./ui/progress.js";
import { renderLocalPageGrid, setDownloadAllHandler } from "./ui/results.js";
import { clearResultsGrid, resultsGrid, showProcessingView, showResultsView, showUploadView } from "./ui/sections.js";
import { bindFilePickerButton, bindUploadZone } from "./ui/upload-zone.js";
import { engine, shutdownEngine } from "./workers/engine-loader.js";

const panel = createProcessingPanel();

/** Set once the warm engine worker has answered its `ping` probe. */
let engineReady = false;

onReady(init);

function init() {
  setDebug(new URLSearchParams(window.location.search).has("debug"));

  const fileInput = $("fileInput");
  const scanButton = $("btnPdf");

  // The scan button stays disabled until the engine is warm: a click before
  // that would have to fail, and the status line explains why.
  if (scanButton) scanButton.disabled = true;

  engine.ready(
    (info) => {
      engineReady = true;
      const status = $("engineStatus");
      if (status) status.textContent = `\u25CF Scan engine ready (${info.source})`;
      if (scanButton && !getState().busy) scanButton.disabled = false;
      logger.info("engine ready", info.source);
    },
    (error) => {
      const status = $("engineStatus");
      const message = error && error.message ? error.message : String(error);
      if (status) status.textContent = `\u25CF Engine failed to load: ${message}`;
      logger.error("engine warm-up failed", error);
    },
  );

  bindUploadZone({
    zone: $("uploadZone"),
    input: fileInput,
    accept: ACCEPT.pdfOnly,
    multiple: false,
    onFiles: (files) => handleFile(files[0]),
  });

  bindFilePickerButton({
    button: scanButton,
    input: fileInput,
    accept: ACCEPT.pdfOnly,
    multiple: false,
  });

  const scanMore = $("btnScanMore");
  if (scanMore) scanMore.addEventListener("click", resetToUpload);

  // Releasing the engine worker on unload keeps the next visit clean.
  window.addEventListener("pagehide", shutdownEngine);

  logger.debug("on-device scan page ready");
}

/**
 * Ask for the page limit, then run the on-device scan.
 *
 * @param {File} file
 */
async function handleFile(file) {
  if (!file || getState().busy) return;

  let pageLimit;
  try {
    pageLimit = await askPageLimit();
  } catch (error) {
    resetToUpload();
    return;
  }

  try {
    assertLocalScanAvailable(file, engineReady, PDF_PROFILES.full);
  } catch (error) {
    notifyScanFailure(error);
    return;
  }

  const state = getState();
  state.busy = true;
  showProcessingView();
  panel.reset();
  setScanButtonEnabled(false);

  try {
    const { bytes, pageImages } = await runOnDevicePdfScan(file, pageLimit, panel, PDF_PROFILES.full);
    const blobUrl = setLocalPdfBlob(new Blob([bytes], { type: "application/pdf" }));
    const downloadName =
      `${safeFilename(String(file.name || "").replace(/\.pdf$/i, ""), "scanned_document")}.pdf`;

    setDownloadAllHandler($("btnDownloadAll"), () => downloadUrl(blobUrl, downloadName));
    clearResultsGrid();
    renderLocalPageGrid(resultsGrid(), file.name, pageImages);
    showResultsView();
  } catch (error) {
    notifyScanFailure(error);
  } finally {
    state.busy = false;
    setScanButtonEnabled(engineReady);
  }
}

/** Show a failure in the step log (the page has no dialog-free error slot). */
function notifyScanFailure(error) {
  const message = error && error.message ? error.message : String(error);
  logger.error("on-device scan failed", error);
  panel.beginStep("Scan failed");
  panel.finishStep(`Error: ${message}`);
  panel.title("Scan failed \u2014 try again");
}

/** @param {boolean} enabled */
function setScanButtonEnabled(enabled) {
  const scanButton = $("btnPdf");
  if (scanButton) scanButton.disabled = !enabled;
}

/** "Scan more": clear results and return to the upload view. */
function resetToUpload() {
  if (getState().busy) return;
  resetResults();
  clearResultsGrid();
  setDownloadAllHandler($("btnDownloadAll"), null);
  panel.reset();
  showUploadView();
}
