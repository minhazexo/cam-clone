/**
 * Page-limit modal ("How many pages to scan?").
 *
 * The modal markup is a shared partial (`templates/partials/page_limit_modal.html`)
 * used by both pages, and this module is its only controller — previously both
 * `app.js` and `scanpdf.js` carried an identical copy of this logic.
 *
 * `askPageLimit()` resolves with the chosen limit (`number`) or `null` for
 * "all pages", and rejects when the user cancels. Rejecting (rather than
 * resolving null) is how callers distinguish "all pages" from "cancelled".
 */

import { $ } from "../core/dom.js";

const IDS = {
  backdrop: "pageLimitBackdrop",
  options: "pageLimitOptions",
  cancel: "pageLimitCancel",
};

/** How long the chosen option stays highlighted before the modal closes. */
const CONFIRM_DELAY_MS = 220;

/**
 * Ask the user how many pages to scan.
 *
 * @returns {Promise<number|null>} chosen limit, or null for "all pages"
 * @throws {Error} when the user cancels or closes the modal
 */
export function askPageLimit() {
  return new Promise((resolve, reject) => {
    const backdrop = $(IDS.backdrop);
    const options = $(IDS.options);
    const cancelButton = $(IDS.cancel);

    if (!backdrop || !options) {
      // No modal in the DOM (stale cached page): scan everything.
      resolve(null);
      return;
    }

    options.querySelectorAll(".page-opt-btn").forEach((button) => {
      button.classList.remove("selected");
    });
    backdrop.classList.remove("hidden");

    function cleanup() {
      backdrop.classList.add("hidden");
      options.removeEventListener("click", onOption);
      if (cancelButton) cancelButton.removeEventListener("click", onCancel);
      backdrop.removeEventListener("click", onBackdrop);
    }

    function onOption(event) {
      const button = event.target.closest(".page-opt-btn");
      if (!button) return;
      options.querySelectorAll(".page-opt-btn").forEach((other) => {
        other.classList.remove("selected");
      });
      button.classList.add("selected");
      const raw = button.dataset.limit;
      const limit = raw === "all" || !raw ? null : parseInt(raw, 10);
      setTimeout(() => {
        cleanup();
        resolve(limit);
      }, CONFIRM_DELAY_MS);
    }

    function onCancel() {
      cleanup();
      reject(new Error("cancelled"));
    }

    function onBackdrop(event) {
      if (event.target === backdrop) onCancel();
    }

    options.addEventListener("click", onOption);
    if (cancelButton) cancelButton.addEventListener("click", onCancel);
    backdrop.addEventListener("click", onBackdrop);
  });
}
