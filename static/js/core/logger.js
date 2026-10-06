/**
 * Tiny logger so frontend diagnostics are greppable and can be silenced.
 *
 * Everything goes through `logger.*` instead of raw `console.*` so a single
 * flag turns debug output on/off, and so failure paths always log with the
 * same `[rscan]` prefix. `logger.error` is used for real failures (the user is
 * also notified through `ui/notifications.js`); `logger.debug` is noise only.
 */

const PREFIX = "[rscan]";

let debugEnabled = false;

/** Enable/disable debug-level output (wired to a `?debug=1` query flag). */
export function setDebug(enabled) {
  debugEnabled = Boolean(enabled);
}

/** True when debug logging is on. */
export function isDebug() {
  return debugEnabled;
}

function emit(method, args) {
  if (typeof console === "undefined" || typeof console[method] !== "function") return;
  console[method](PREFIX, ...args);
}

export const logger = {
  /** Verbose tracing; only shown with debug enabled. */
  debug(...args) {
    if (debugEnabled) emit("log", args);
  },
  /** Normal progress information (kept visible: useful in bug reports). */
  info(...args) {
    emit("log", args);
  },
  /** Recoverable problem (a fallback is about to run). */
  warn(...args) {
    emit("warn", args);
  },
  /** Failure; always paired with a user-visible notification somewhere. */
  error(...args) {
    emit("error", args);
  },
};
