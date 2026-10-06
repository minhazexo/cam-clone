/**
 * Static asset contract test (bun test).
 *
 * The frontend loads assets by absolute path (`/static/...`) from three
 * places that can drift apart: `core/constants.js`, the Jinja templates, and
 * the scan worker's `importScripts`. This test asserts every path exists on
 * disk, so renaming a worker or a vendor file fails here instead of in the
 * browser.
 *
 * Run: bun test tests/js
 */

import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";

const ROOT = resolve(import.meta.dir, "..", "..");
const STATIC = join(ROOT, "static");

const constants = readFileSync(join(STATIC, "js", "core", "constants.js"), "utf8");

/**
 * Extract quoted `/static/...` paths from a source string.
 *
 * Comments are stripped first: the docs in these files legitimately mention
 * paths like `/static/...` as prose, which are not real assets.
 */
function staticPathsIn(source) {
  const withoutComments = source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|\s)\/\/[^\n]*/g, "$1");
  const matches = withoutComments.matchAll(/["'`](\/static\/[^"'`]+)["'`]/g);
  return [...matches].map((match) => match[1]);
}

/** Map a `/static/x/y` URL to a file path under static/. */
function toDiskPath(url) {
  return join(STATIC, url.replace(/^\/static\//, ""));
}

describe("frontend asset paths", () => {
  test("every /static path in core/constants.js exists", () => {
    const paths = staticPathsIn(constants);
    expect(paths.length).toBeGreaterThan(3);
    for (const url of paths) {
      expect(existsSync(toDiskPath(url)), `missing asset: ${url}`).toBe(true);
    }
  });

  test("templates reference only existing static assets", () => {
    const templatesDir = join(ROOT, "templates");
    const templates = [];
    const walk = (dir) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.name.endsWith(".html")) templates.push(full);
      }
    };
    walk(templatesDir);

    expect(templates.length).toBeGreaterThan(3);
    for (const file of templates) {
      const source = readFileSync(file, "utf8");
      for (const url of staticPathsIn(source)) {
        expect(existsSync(toDiskPath(url)), `${file} -> ${url}`).toBe(true);
      }
    }
  });

  test("scan worker imports the geometry module from its new path", () => {
    const worker = readFileSync(join(STATIC, "js", "workers", "scan-worker-v2.js"), "utf8");
    for (const url of staticPathsIn(worker)) {
      expect(existsSync(toDiskPath(url)), `worker imports missing asset: ${url}`).toBe(true);
    }
  });

  test("ES module imports resolve to existing files", () => {
    const jsRoot = join(STATIC, "js");
    const files = [];
    const walk = (dir) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.name.endsWith(".js")) files.push(full);
      }
    };
    walk(jsRoot);

    const isModule = (source) => /^\s*(import|export)\s/m.test(source);
    for (const file of files) {
      const source = readFileSync(file, "utf8");
      if (!isModule(source)) continue; // classic worker scripts use importScripts
      for (const match of source.matchAll(/from\s+["'](\.[^"']+)["']/g)) {
        const target = resolve(file, "..", match[1]);
        expect(existsSync(target), `${file} imports missing ${match[1]}`).toBe(true);
      }
    }
  });
});
