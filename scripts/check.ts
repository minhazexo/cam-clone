const required = [
  "static/vendor/runtime.js",
  "static/vendor/pdf.worker.js",
];

for (const path of required) {
  if (!(await Bun.file(path).exists())) {
    console.error(`Missing Bun build artifact: ${path}`);
    process.exit(1);
  }
}

console.log("Bun artifacts are present.");
