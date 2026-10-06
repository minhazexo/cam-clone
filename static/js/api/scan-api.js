/**
 * Image scan API client.
 *
 * `POST /api/scan` takes one multipart field named `files` (repeated) and
 * answers `{"pages": [...]}` where each page is either a result descriptor
 * (`{name, id, width, height}`) or a per-file error (`{name, error}`).
 */

import { ENDPOINTS } from "../core/constants.js";
import { postForm } from "./client.js";

/**
 * Scan one or more image files.
 *
 * @param {File[]|FileList} files
 * @returns {Promise<Array<{name: string, id?: string, width?: number, height?: number, error?: string}>>}
 */
export async function scanImages(files) {
  const formData = new FormData();
  Array.from(files).forEach((file) => formData.append("files", file));
  const payload = await postForm(ENDPOINTS.scan, formData);
  return payload.pages || [];
}

/** URL of a scanned image artifact. */
export function imageUrl(id) {
  return ENDPOINTS.image(id);
}
