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
import {
  PDF_PROFILES, ENDPOINTS, LIMITS, SCAN_POOL, THUMBNAIL_MAX_SIDE,
  scanPoolPlan, usableCores,
} from "../../static/js/core/constants.js";
import { planPageChunks } from "../../static/js/features/pdf-scan/pdf-processing.js";

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
    // Pixel budget: width caps alone let long receipts/plots render past
    // what the scan worker's WASM heap can hold (canvas budget is the
    // second line of defence — REF_CANVAS_MAX_PIXELS in the scanner).
    expect(PDF_PROFILES.full.maxPagePixels).toBe(12000000);
    expect(PDF_PROFILES.fallback.maxPagePixels).toBeNull();
    expect(PDF_PROFILES.fallback.drawBorder).toBe(false);
    expect(PDF_PROFILES.fallback.jpegQuality).toBeGreaterThan(PDF_PROFILES.full.jpegQuality);
  });

  test("local limits match the documented 250 MB / 250 pages", () => {
    expect(LIMITS.maxLocalPdfBytes).toBe(250 * 1024 * 1024);
    expect(LIMITS.maxLocalPdfPages).toBe(250);
  });

  test("every scanned page keeps a small thumbnail (the grid shows all pages)", () => {
    // The old 12-thumbnail count cap is gone: previews are downscaled
    // instead, so a full-length document cannot blow up memory while the
    // results grid still shows every page.
    expect(LIMITS.maxThumbnails).toBeUndefined();
    expect(THUMBNAIL_MAX_SIDE).toBe(960);
  });
});

describe("scanPoolPlan", () => {
  const full = PDF_PROFILES.full;
  const fallback = PDF_PROFILES.fallback;
  const plan = (overrides) => scanPoolPlan({
    pageCount: 40, hardwareConcurrency: 8, profile: full, ...overrides,
  });

  test("the fallback profile stays single-worker (legacy behaviour)", () => {
    expect(plan({ profile: fallback })).toEqual({
      workers: 1,
      reason: "fallback profile uses a single light worker",
    });
  });

  test("a single page never spawns extra engines, and says so", () => {
    expect(plan({ pageCount: 1 })).toEqual({ workers: 1, reason: "only one page to scan" });
    expect(plan({ pageCount: 0 }).workers).toBe(1);
    expect(plan({ pageCount: NaN }).workers).toBe(1);
  });

  test("every core scans below the spare-core threshold", () => {
    expect(usableCores(1)).toBe(1);
    expect(usableCores(3)).toBe(3);
    expect(usableCores(4)).toBe(4);
    expect(usableCores(SCAN_POOL.spareCoreThreshold)).toBe(
      SCAN_POOL.spareCoreThreshold - SCAN_POOL.reservedCores);
    // A 4-core machine gets four workers, not three: there is no spare core.
    expect(plan({ hardwareConcurrency: 4 }).workers)
      .toBe(Math.min(SCAN_POOL.maxWorkers, usableCores(4)));
    expect(plan({ hardwareConcurrency: 4 }).reason).toBe("4 cores");
  });

  test("big machines are held by the memory cap", () => {
    const p = plan({ hardwareConcurrency: 32 });
    expect(p.workers).toBe(SCAN_POOL.maxWorkers);
    expect(p.reason).toBe("memory cap");
  });

  test("never asks for more workers than there are pages (the 'why only 2?' case)", () => {
    const p = plan({ pageCount: 2, hardwareConcurrency: 16 });
    expect(p.workers).toBe(2);
    expect(p.reason).toBe("only 2 pages");
    expect(plan({ pageCount: 3, hardwareConcurrency: 16 }).workers).toBe(3);
  });

  test("small screens get a smaller pool, labelled as such", () => {
    const p = plan({ pageCount: 40, hardwareConcurrency: 16, smallScreen: true });
    expect(p.workers).toBe(SCAN_POOL.maxWorkersSmallScreen);
    expect(p.reason).toBe("small screen");
    expect(SCAN_POOL.maxWorkersSmallScreen).toBeLessThan(SCAN_POOL.maxWorkers);
  });

  test("an unknown core count assumes a quad core instead of going single", () => {
    expect(SCAN_POOL.fallbackCores).toBe(4);
    expect(plan({ hardwareConcurrency: undefined }).workers)
      .toBe(Math.min(SCAN_POOL.maxWorkers, usableCores(SCAN_POOL.fallbackCores)));
  });

  test("a single-core machine is told exactly that", () => {
    expect(plan({ hardwareConcurrency: 1 })).toEqual({ workers: 1, reason: "single CPU core" });
  });
});

describe("planPageChunks", () => {
  test("splits pages into ordered chunks of pool size", () => {
    expect(planPageChunks(10, 4)).toEqual([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10]]);
  });

  test("a single worker degenerates to one page at a time", () => {
    expect(planPageChunks(3, 1)).toEqual([[1], [2], [3]]);
  });

  test("a pool larger than the document scans everything in one go", () => {
    expect(planPageChunks(3, 8)).toEqual([[1, 2, 3]]);
  });

  test("covers every page exactly once, in document order", () => {
    const flat = planPageChunks(250, 4).flat();
    expect(flat).toEqual(Array.from({ length: 250 }, (_, i) => i + 1));
  });

  test("handles no pages and nonsense sizes", () => {
    expect(planPageChunks(0, 4)).toEqual([]);
    expect(planPageChunks(3, 0)).toEqual([[1], [2], [3]]);
    expect(planPageChunks(3, undefined)).toEqual([[1], [2], [3]]);
  });
});
