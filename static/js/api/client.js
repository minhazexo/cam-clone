/**
 * Shared HTTP client used by every API module.
 *
 * Responsibilities (and nothing else): build the request, parse JSON safely,
 * translate non-2xx responses into `ApiError` with the server's `error`
 * message, and normalise network failures. Feature modules therefore never
 * handle `res.ok` or JSON parse errors themselves.
 */

import { ApiError } from "../core/errors.js";
import { logger } from "../core/logger.js";

/**
 * Perform a request and parse a JSON body.
 *
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<object>} parsed JSON payload
 * @throws {ApiError} on network failure, non-2xx status, or `{error}` body
 */
export async function requestJson(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    logger.error("request failed", url, error);
    throw new ApiError(
      "Could not reach the scan server. Check your connection and try again.",
      { cause: error },
    );
  }

  const payload = await readJson(response);

  if (!response.ok || (payload && payload.error)) {
    const message =
      (payload && payload.error) || `Request failed (HTTP ${response.status})`;
    throw new ApiError(message, { status: response.status });
  }
  return payload || {};
}

/**
 * Read a JSON body without throwing on empty/invalid payloads.
 *
 * @param {Response} response
 * @returns {Promise<object|null>}
 */
export async function readJson(response) {
  try {
    return await response.json();
  } catch (error) {
    logger.debug("response was not JSON", response.url, error);
    return null;
  }
}

/**
 * POST a multipart form.
 *
 * @param {string} url
 * @param {FormData} formData
 * @returns {Promise<object>}
 */
export function postForm(url, formData) {
  return requestJson(url, { method: "POST", body: formData });
}

/**
 * GET a JSON endpoint that may legitimately fail (used for health checks).
 *
 * @param {string} url
 * @param {{timeoutMs?: number}} [options]
 * @returns {Promise<boolean>} true when the endpoint answered 2xx JSON
 */
export async function ping(url, options = {}) {
  const timeoutMs = options.timeoutMs || 0;
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timer = controller && timeoutMs
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;
  try {
    const response = await fetch(url, {
      method: "GET",
      signal: controller ? controller.signal : undefined,
    });
    return response.ok;
  } catch (error) {
    logger.debug("ping failed", url, error);
    return false;
  } finally {
    if (timer) clearTimeout(timer);
  }
}
