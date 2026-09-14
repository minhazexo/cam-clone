const builds = [
  {
    entrypoints: ["static/js/runtime.ts"],
    naming: "runtime.js",
    format: "esm",
  },
  {
    entrypoints: ["node_modules/pdfjs-dist/build/pdf.worker.js"],
    naming: "pdf.worker.js",
    format: "iife",
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

console.log("Bun build complete: static/vendor/runtime.js and pdf.worker.js");
