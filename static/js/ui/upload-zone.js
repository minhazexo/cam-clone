/**
 * Upload-zone wiring shared by both pages.
 *
 * This lives in `ui/` (not under a feature folder) because both pages - image
 * scanning on `/` and the on-device PDF page - use the exact same
 * interactions; a per-feature copy would be duplication.
 *
 * Preserves the original interactions exactly:
 *  - drag & drop highlights the zone (`dragover`) and hands files to `onFiles`;
 *  - clicking the zone opens the picker, except when the click lands on a
 *    button inside it (buttons own their own behaviour);
 *  - the picker's `accept`/`multiple` attributes are set per scan mode, which
 *    is how "Scan Images" offers images while the zone still accepts a PDF.
 */

import { ACCEPT } from "../core/constants.js";
import { logger } from "../core/logger.js";

/**
 * @typedef {object} UploadZoneOptions
 * @property {HTMLElement|null} zone drop/click area
 * @property {HTMLInputElement|null} input hidden file input
 * @property {(files: FileList) => void} onFiles called with a new selection
 * @property {string} [accept] initial `accept` attribute
 * @property {boolean} [multiple] initial `multiple` flag
 */

/**
 * Bind drag & drop plus click-to-browse on the upload zone.
 *
 * @param {UploadZoneOptions} options
 */
export function bindUploadZone(options) {
  const { zone, input, onFiles } = options;

  if (input) {
    input.multiple = options.multiple !== false;
    input.accept = options.accept || ACCEPT.all;
    input.addEventListener("change", () => {
      if (input.files && input.files.length) onFiles(input.files);
    });
  }

  if (!zone) return;

  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragover");
    const files = event.dataTransfer && event.dataTransfer.files;
    if (files && files.length && onFiles) onFiles(files);
  });
  zone.addEventListener("click", (event) => {
    if (event.target.closest(".btn")) return;
    if (input) input.click();
  });
}

/**
 * Bind a scan-mode button to the file picker.
 *
 * @param {object} options
 * @param {HTMLElement|null} options.button
 * @param {HTMLInputElement|null} options.input
 * @param {string} options.accept `accept` attribute for this mode
 * @param {boolean} [options.multiple]
 */
export function bindFilePickerButton(options) {
  const { button, input, accept, multiple } = options;
  if (!button || !input) return;
  button.addEventListener("click", (event) => {
    event.stopPropagation(); // never let the zone's click handler double-open
    input.accept = accept;
    input.multiple = multiple !== false;
    logger.debug("file picker opened", accept);
    input.click();
  });
}

/** Reset the input so picking the same file twice fires `change` again. */
export function resetFileInput(input) {
  if (input) input.value = "";
}
