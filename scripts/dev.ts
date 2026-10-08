/**
 * Local dev launcher (`bun run dev`).
 *
 * Cross-platform replacement for the old `sh -c 'PY=...'` chain, which fails
 * on Windows (PowerShell has no `sh`). Bun executes this file on every OS:
 * it finds a Python interpreter (`python3` preferred, `python` fallback) and
 * runs `app.py` with inherited stdio, so logs and Ctrl+C behave normally.
 *
 * Vercel never runs this: production is served from `api/index.py` via
 * `vercel.json` (no build command, no bun scripts).
 */

// Prefer the project venv (see docs/DEPLOYMENT.md), then fall back to PATH.
const venvPy = process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python";
const candidates = process.platform === "win32" ? ["python", "python3"] : ["python3", "python"];

let py: string | null = null;
if (await Bun.file(venvPy).exists()) {
  py = venvPy;
} else {
  for (const name of candidates) {
    if (Bun.which(name)) {
      py = name;
      break;
    }
  }
}

if (!py) {
  console.error(
    "No Python interpreter found (`python3` or `python`). " +
      "Install Python, then run `pip install -r requirements.txt`.",
  );
  process.exit(1);
}

const child = Bun.spawn([py, "app.py"], {
  stdio: ["inherit", "inherit", "inherit"],
});

process.exit(await child.exited);
