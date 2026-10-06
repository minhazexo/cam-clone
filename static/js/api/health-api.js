/**
 * Health probe client.
 *
 * `GET /api/health` answers `{"status": "ok", "service": "rscan"}`. It is used
 * as a *diagnostic* when a server scan fails, so the logged reason can tell a
 * dead backend from a rejected upload, and as the deploy verification step in
 * `docs/DEPLOYMENT.md`.
 */

import { ENDPOINTS } from "../core/constants.js";
import { ping } from "./client.js";

/**
 * Is the scan server reachable?
 *
 * @param {number} [timeoutMs] abort the probe after this long (0 = no limit)
 * @returns {Promise<boolean>}
 */
export function checkServerHealth(timeoutMs = 3000) {
  return ping(ENDPOINTS.health, { timeoutMs });
}
