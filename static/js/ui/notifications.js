/**
 * User notifications.
 *
 * The current product surfaces errors and confirmations with the browser's
 * native dialogs (`alert`). That behaviour is preserved here on purpose: it is
 * part of the shipped UX, and this module is the single seam to replace later
 * with in-page toasts without touching any feature module.
 */

import { logger } from "../core/logger.js";

/**
 * Show an error to the user (blocking dialog, as before).
 *
 * @param {string} message
 */
export function notifyError(message) {
  logger.warn("notify error", message);
  window.alert(message);
}

/**
 * Show an informational message (blocking dialog, as before).
 *
 * @param {string} message
 */
export function notifyInfo(message) {
  window.alert(message);
}
