const builds = [
  {
    entrypoints: ["static/js/runtime.ts"],
    naming: "runtime.js",
    format: "esm",
  },
];

for (const config of builds) {
  const result = await Bun.build({
    ...config,
    outdir: "static/vendor",
    target: "browser",
    minify: true,
    sourcemap: "external",
  });

  if (!result.success) {
    for (const log of result.logs) console.error(log);
    process.exit(1);
  }
}

// pdf.worker.js is COPIED verbatim, never bundled: it must match the legacy
// API build byte-for-byte in protocol, and rebundling breaks its worker
// bootstrap (getDocument() then hangs forever with no error).
await Bun.write(
  "static/vendor/pdf.worker.js",
  Bun.file("node_modules/pdfjs-dist/legacy/build/pdf.worker.js")
);

console.log("Bun build complete: static/vendor/runtime.js and pdf.worker.js");
