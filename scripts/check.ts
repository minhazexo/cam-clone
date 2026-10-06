/**
 * Frontend asset gate (`bun run check`).
 *
 * The pages load vendored libraries and worker scripts by absolute path
 * (`static/vendor/...`, `static/js/workers/...`). Those paths are part of the
 * runtime contract: this script fails fast (before the parity suite, before a
 * deploy) when a required artifact is missing.
 *
 * `tests/js/assets.test.js` additionally cross-checks that every path the
 * frontend code mentions resolves to a file.
 */

const required = [
  // Vendored libraries (see scripts/build.ts and docs/FRONTEND_ARCHITECTURE.md)
  "static/vendor/runtime.js",
  "static/vendor/pdf.worker.js",
  "static/vendor/opencv.js",
  // Worker layer: the OpenCV.js pipeline and the Node parity harness entry
  "static/js/workers/scan-worker.js",
  "static/js/workers/scan-worker-v2.js",
  "static/js/workers/scan-geometry.js",
  // Page entrypoints (ES modules imported by the templates)
  "static/js/app.js",
  "static/js/scanpdf.js",
];

let missing = 0;
for (const path of required) {
  if (!(await Bun.file(path).exists())) {
    console.error(`Missing frontend artifact: ${path}`);
    missing += 1;
  }
}

if (missing > 0) {
  console.error(
    `\n${missing} required asset(s) missing. ` +
      "Run `bun run build` to rebuild vendor artifacts, " +
      "and check that worker files were not moved (see AGENTS.md -> invariants).",
  );
  process.exit(1);
}

console.log(`Frontend artifacts present (${required.length} checked).`);
