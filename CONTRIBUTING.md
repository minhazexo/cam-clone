# Contributing to RScan

Thanks for helping improve RScan. This document covers how to propose changes safely.

## Before you start

1. Search [existing issues](https://github.com/minhazexo/cam-clone/issues) and PRs.
2. For large changes (new pipeline stages, API shape, deploy model), open an issue first to discuss direction.
3. Read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Development setup

```bash
git clone https://github.com/minhazexo/cam-clone.git
cd cam-clone
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
bun install
bun run build
python app.py                    # http://localhost:5000
```

## Branches & commits

- Branch from `master`.
- Use concise, imperative subjects: `Fix EXIF rotation on JPEG uploads`, not `fixed stuff`.
- Keep commits focused — one logical change per commit when practical.

## What must pass before a PR

Run the same gates CI runs:

```bash
bun run check      # vendor artifacts present
bun run parity     # worker + geometry + full parity harnesses
python -m compileall -q app.py api RScan/Python/scan
```

If you change the scan pipeline (`RScan/Python/scan/*`) or the JS port (`static/js/scan-worker-v2.js`, `scan-geometry.js`):

- Regenerate fixtures when intentional: `python scripts/gen_fixtures.py`
- Explain the quality impact in the PR (why fixtures moved, expected MAD / sharpness deltas).

## Pull requests

- Fill in the PR template (what / why / how tested).
- Link related issues (`Fixes #123`).
- Keep diffs reviewable — separate refactors from behavior changes.
- Do not commit: `.env`, secrets, `node_modules/`, `.venv/`, large test PDFs, generated `docs/` (already git-ignored).

## Reporting bugs

Use the **Bug report** issue template and include:

- OS + Python version + browser (for UI bugs)
- Exact steps, expected vs actual result
- A minimal sample file if it can be shared (redact sensitive documents)

## Security issues

Do **not** open a public issue. Follow [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the project’s [GPL-3.0](LICENSE) license.
