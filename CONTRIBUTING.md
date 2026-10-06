# Contributing to RScan

Thanks for helping improve RScan. This document covers how to propose changes
safely. If you are an AI agent (or working with one), read
[AGENTS.md](AGENTS.md) first — it is the map of the repository and the list of
invariants.

## Before you start

1. Search [existing issues](https://github.com/minhazexo/cam-clone/issues) and PRs.
2. For large changes (new pipeline stages, API shape, deploy model), open an
   issue first to discuss direction.
3. Read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Development setup

```bash
git clone https://github.com/minhazexo/cam-clone.git
cd cam-clone
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
bun install
bun run build                    # optional: rebuilds static/vendor artifacts
python app.py                    # http://localhost:5000
```

## Repository orientation

| Area | Start here |
|---|---|
| HTTP layer, routes | `rscan/web/routes/` |
| Scan use-cases | `rscan/services/` |
| **Scanner algorithm** | `rscan/scanner/` (+ `static/js/workers/` mirror) |
| PDF rendering/assembly | `rscan/pdf/` |
| Jobs and progress | `rscan/jobs/` |
| Frontend pages | `static/js/app.js`, `static/js/scanpdf.js` |
| Frontend modules | `static/js/{core,api,ui,features}/` |
| Layout and UI shell | `templates/layouts/`, `templates/partials/` |
| Tests | `tests/{unit,integration,js,parity}/` |

Architecture, API, pipelines, testing and deployment each have a document in
[`docs/`](docs/). The AI-facing CHANGE MAP lives in [AGENTS.md](AGENTS.md).

## Branches & commits

- Branch from `master`.
- Use concise, imperative subjects: `Fix EXIF rotation on JPEG uploads`, not
  `fixed stuff`.
- Keep commits focused — one logical change per commit when practical.

## What must pass before a PR

```bash
bun run test        # asset gate + parity + JS tests + Python unit/integration
```

Individual lanes, when you only touched one area:

```bash
bun run check && bun run test:js      # frontend
bun run test:python                   # backend
bun run parity                        # scanner / worker changes
python -m compileall -q app.py api rscan RScan/Python/scan scripts
```

## Changing the scanner (parity rules)

The image pipeline exists twice: `rscan/scanner/**` (Python) and
`static/js/workers/**` (JavaScript/WASM). `bun run parity` compares the JS
output against fixtures produced by the Python pipeline.

If you change scan behaviour:

- mirror the change on the other side (same constants, same operation order,
  same rounding);
- keep the change behaviour-preserving unless the PR is explicitly about
  quality;
- regenerate fixtures only when the change is intentional:

```bash
python scripts/gen_fixtures.py
python scripts/dump_stages.py
python scripts/dump_rgb.py
```

- explain the quality impact in the PR (why fixtures moved, expected MAD /
  sharpness deltas). Do not "fix" a parity failure by loosening thresholds.

Update `docs/SCAN_PIPELINE.md` when stage order, constants, or the worker
protocol change.

## Adding an API endpoint

1. Add a route module in `rscan/web/routes/` and register its blueprint in
   `routes/__init__.py` — routes validate, call a service, and return a response.
2. Put the logic in `rscan/services/` (no Flask imports there).
3. Add a client in `static/js/api/` and the endpoint to
   `static/js/core/constants.js` if the frontend uses it.
4. Document it in `docs/API.md` and cover it in
   `tests/integration/test_web_flows.py`.

## Frontend rules

- Constants live in `static/js/core/constants.js` — never hardcode a limit or an
  `/api`/`/static` path in a feature module.
- Template element ids are a contract with the frontend modules; renames must
  update the partial and the module together
  (`docs/FRONTEND_ARCHITECTURE.md` has the table).
- Keep the worker layer classic (`importScripts`): it must stay loadable by both
  the browser and the Node parity harnesses.

## Pull requests

- Fill in the PR template (what / why / how tested).
- Link related issues (`Fixes #123`).
- Keep diffs reviewable — separate refactors from behaviour changes.
- Do not commit: `.env`, secrets, `node_modules/`, `.venv/`, large test PDFs, or
  scanned outputs (`scanned_*.pdf`).

## Reporting bugs

Use the **Bug report** issue template and include OS, Python version, browser
(for UI bugs), exact steps, expected vs actual result, and a minimal sample file
if it can be shared (redact sensitive documents).

## Security issues

Do **not** open a public issue. Follow [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the
project's [GPL-3.0](LICENSE) license.
