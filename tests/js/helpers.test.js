/**
 * Unit tests for the pure frontend helpers (bun test).
 *
 * Only DOM-free helpers are covered here: anything that calls
 * `document.createElement` needs a real browser and is verified through the
 * pages instead (see docs/TESTING.md).
 *
 * Run: bun test tests/js
 */

import { describe, expect, test } from "bun:test";

import { formatBytes, safeFilename } from "../../static/js/core/dom.js";
import { AppError, toUserMessage } from "../../static/js/core/errors.js";
import { selectionSignature } from "../../static/js/core/state.js";
import { PDF_PROFILES, ENDPOINTS, LIMITS } from "../../static/js/core/constants.js";

describe("safeFilename", () => {
  test("keeps safe characters and extensions", () => {
    expect(safeFilename("report_v2.pdf", "fallback")).toBe("report_v2.pdf");
  });

  test("collapses runs of unsafe characters to a single underscore", () => {
    expect(safeFilename("my report (final).pdf", "fallback")).toBe("my_report_final_.pdf");
  });

  test("removes path separators and leading dots", () => {
    // Separators are replaced, so a traversal string can never survive as a
    // path - it is only ever used as a `download` attribute anyway.
    expect(safeFilename("../../etc/passwd", "fallback")).toBe("_.._etc_passwd");
    expect(safeFilename(".hidden", "fallback")).toBe("hidden");
  });

  test("falls back when the name is empty", () => {
    expect(safeFilename("", "scanned_page")).toBe("scanned_page");
    expect(safeFilename(null, "scanned_page")).toBe("scanned_page");
    expect(safeFilename(undefined, "scanned_page")).toBe("scanned_page");
  });
});

describe("formatBytes", () => {
  test("formats bytes, kilobytes and megabytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  test("treats junk as zero", () => {
    expect(formatBytes(undefined)).toBe("0 B");
    expect(formatBytes("nope")).toBe("0 B");
  });
});

describe("error messages", () => {
  test("AppError messages are user-facing", () => {
    expect(toUserMessage(new AppError("Scan failed"))).toBe("Scan failed");
  });

  test("plain errors and strings are handled", () => {
    expect(toUserMessage(new Error("boom"))).toBe("boom");
    expect(toUserMessage("plain")).toBe("plain");
  });
});

describe("selectionSignature", () => {
  test("is stable across orderings", () => {
    const a = { name: "a.jpg", size: 1, lastModified: 10 };
    const b = { name: "b.jpg", size: 2, lastModified: 20 };
    expect(selectionSignature([a, b])).toBe(selectionSignature([b, a]));
  });

  test("changes when a file changes", () => {
    const a = { name: "a.jpg", size: 1, lastModified: 10 };
    const b = { name: "a.jpg", size: 1, lastModified: 11 };
    expect(selectionSignature([a])).not.toBe(selectionSignature([b]));
  });
});

describe("constants contract", () => {
  test("endpoint builders encode their path segment", () => {
    expect(ENDPOINTS.image("a b")).toBe("/api/image/a%20b");
    expect(ENDPOINTS.pdf("scanned_1.pdf")).toBe("/api/pdf/scanned_1.pdf");
    expect(ENDPOINTS.scanPdfProgress("j1")).toBe("/api/scan-pdf-progress/j1");
  });

  test("the two PDF profiles keep their documented differences", () => {
    expect(PDF_PROFILES.full.renderDpi).toBe(200);
    expect(PDF_PROFILES.full.pageMode).toBe("a4");
    expect(PDF_PROFILES.full.drawBorder).toBe(true);
    expect(PDF_PROFILES.fallback.pageMode).toBe("source");
    expect(PDF_PROFILES.fallback.drawBorder).toBe(false);
    expect(PDF_PROFILES.fallback.jpegQuality).toBeGreaterThan(PDF_PROFILES.full.jpegQuality);
  });

  test("local limits match the documented 250 MB / 250 pages", () => {
    expect(LIMITS.maxLocalPdfBytes).toBe(250 * 1024 * 1024);
    expect(LIMITS.maxLocalPdfPages).toBe(250);
  });
});
