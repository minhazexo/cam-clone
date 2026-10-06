/**
 * Page shell: which of the three sections is visible.
 *
 * Both pages render the same shell (`uploadSection`, `processingSection`,
 * `resultsSection`), so visibility switching lives here instead of being
 * duplicated per page. Ids are the Jinja partial contract — see
 * `templates/partials/`.
 */

import { $, clearChildren, hide, show } from "../core/dom.js";

/** Element ids of the page shell (single place to look them up). */
export const SECTION_IDS = {
  upload: "uploadSection",
  processing: "processingSection",
  results: "resultsSection",
  resultsGrid: "resultsGrid",
};

function setVisible(...visibleKeys) {
  Object.entries(SECTION_IDS).forEach(([key, id]) => {
    if (key === "resultsGrid") return;
    const element = $(id);
    if (!element) return;
    if (visibleKeys.includes(key)) show(element);
    else hide(element);
  });
}

/** Show the upload zone and hide processing/results. */
export function showUploadView() {
  setVisible("upload");
}

/** Show the processing panel and hide upload/results. */
export function showProcessingView() {
  setVisible("processing");
}

/** Show the results grid and hide upload/processing. */
export function showResultsView() {
  setVisible("results");
}

/** Empty the results grid (called before rendering new results). */
export function clearResultsGrid() {
  clearChildren($(SECTION_IDS.resultsGrid));
}

/** The results grid element (may be null on a stale cached page). */
export function resultsGrid() {
  return $(SECTION_IDS.resultsGrid);
}
