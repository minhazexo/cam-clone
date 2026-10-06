/**
 * Centralised frontend error types and user-message mapping.
 *
 * Why: the UI has three very different failure sources (HTTP API, PDF engine,
 * local pipeline). Each raises a typed error here, and the entrypoints decide
 * what to do with it — fall back, notify, or just log. Messages are written
 * for users; technical detail goes to `logger.error`.
 */

import { logger } from "./logger.js";

/** Base class so callers can `instanceof AppError` for anything expected. */
export class AppError extends Error {
  /**
   * @param {string} message user-facing message
   * @param {{cause?: unknown, code?: string}} [options]
   */
  constructor(message, options = {}) {
    super(message);
    this.name = new.target.name;
    this.code = options.code || "app_error";
    if (options.cause !== undefined) this.cause = options.cause;
  }
}

/** The PDF/WASM engine has not finished loading (or failed to load). */
export class EngineUnavailableError extends AppError {
  constructor(message = "Scan engine is still loading. Please try again in a moment.") {
    super(message, { code: "engine_unavailable" });
  }
}

/** The selected file cannot be processed locally (size/page limits). */
export class LocalPdfLimitError extends AppError {
  constructor(message) {
    super(message, { code: "local_pdf_limit" });
  }
}

/** A server request failed (HTTP error or an `{error}` JSON body). */
export class ApiError extends AppError {
  /**
   * @param {string} message
   * @param {{status?: number, cause?: unknown}} [options]
   */
  constructor(message, options = {}) {
    super(message, { code: "api_error", cause: options.cause });
    this.status = options.status;
  }
}

/** The SSE progress stream closed or errored before the job finished. */
export class ProgressStreamError extends AppError {
  constructor(message = "Connection to the scan server was lost. Please try again.") {
    super(message, { code: "progress_stream" });
  }
}

/**
 * Turn any thrown value into a user-facing string.
 *
 * @param {unknown} error
 * @returns {string}
 */
export function toUserMessage(error) {
  if (error instanceof AppError) return error.message;
  if (error && typeof error.message === "string" && error.message) {
    return error.message;
  }
  return String(error);
}

/**
 * Log a failure with context and return the user-facing message.
 *
 * @param {string} context where the failure happened (module/step)
 * @param {unknown} error
 * @returns {string}
 */
export function reportError(context, error) {
  logger.error(context, error);
  return toUserMessage(error);
}
