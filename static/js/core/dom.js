/**
 * DOM helpers shared by every page.
 *
 * The templates are server-rendered Jinja partials, so ids are stable and
 * documented in `docs/FRONTEND_ARCHITECTURE.md`. All lookups are lazily done
 * through `$()` instead of cached at module load: a stale cached-HTML page
 * then degrades gracefully instead of throwing on a missing element.
 */

/**
 * `document.getElementById` shorthand.
 *
 * @param {string} id
 * @returns {HTMLElement|null}
 */
export function $(id) {
  return document.getElementById(id);
}

/**
 * Run `fn` once the DOM is ready (works whether the script is a deferred
 * module — the normal case — or loaded after parsing already finished).
 *
 * @param {() => void} fn
 */
export function onReady(fn) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fn, { once: true });
  } else {
    fn();
  }
}

/**
 * Escape text for safe interpolation into an HTML string.
 *
 * @param {unknown} value
 * @returns {string}
 */
export function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

/**
 * Make a filesystem-safe download name.
 *
 * @param {unknown} name
 * @param {string} fallback used when nothing usable is left
 * @returns {string}
 */
export function safeFilename(name, fallback) {
  const cleaned = String(name || "")
    .replace(/[^a-z0-9._-]+/gi, "_")
    .replace(/^\.+/, "");
  return cleaned || fallback;
}

/**
 * Human-readable byte size (B / KB / MB).
 *
 * @param {number} bytes
 * @returns {string}
 */
export function formatBytes(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

/**
 * Remove every child of `element` (no-op when element is null).
 *
 * @param {Element|null} element
 */
export function clearChildren(element) {
  if (element) element.innerHTML = "";
}

/**
 * Create an element with optional class/text.
 *
 * @param {string} tag
 * @param {string} [className]
 * @param {string} [text]
 * @returns {HTMLElement}
 */
export function createEl(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

/**
 * Trigger a browser download for a URL.
 *
 * @param {string} url
 * @param {string} filename
 */
export function downloadUrl(url, filename) {
  const a = document.createElement("a");
  a.href = url;
  if (filename) a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** Show an element (removes the `hidden` class). */
export function show(element) {
  if (element) element.classList.remove("hidden");
}

/** Hide an element (adds the `hidden` class). */
export function hide(element) {
  if (element) element.classList.add("hidden");
}

/** Toggle the `hidden` class. */
export function setHidden(element, isHidden) {
  if (!element) return;
  element.classList.toggle("hidden", Boolean(isHidden));
}

/** Add/remove a class based on a boolean. */
export function setClass(element, className, enabled) {
  if (element) element.classList.toggle(className, Boolean(enabled));
}

/** Set `textContent` when the element exists. */
export function setText(element, text) {
  if (element) element.textContent = text;
}
