## Summary

<!-- What does this PR change, and why? 1–3 sentences. -->

## Related issues

<!-- e.g. Fixes #123 -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Pipeline / scan-quality change (parity-sensitive)
- [ ] Refactor (no behavior change)
- [ ] Docs or tooling

## How was this tested?

<!-- Commands run, pages exercised, sample files used -->

- [ ] `bun run test` (assets + parity + JS + Python)
- [ ] Individually, if relevant:
  - [ ] `bun run check`
  - [ ] `bun run parity` (required for `rscan/scanner/**` or `static/js/workers/**`)
  - [ ] `bun run test:js`
  - [ ] `bun run test:python`
- [ ] `python -m compileall -q app.py api rscan RScan/Python/scan scripts` (Python changes)
- [ ] Manual UI check on `/` and `/scan-pdf` (frontend changes)

## For pipeline / worker changes

- [ ] The same change was mirrored in both implementations
      (`rscan/scanner/**` ↔ `static/js/workers/**`)
- [ ] Fixture changes (if any) are intentional and explained below
- [ ] Expected MAD / sharpness impact:

## Screenshots (UI changes)

<!-- Before/after if applicable -->

## Checklist

- [ ] I read [CONTRIBUTING.md](../CONTRIBUTING.md) and [AGENTS.md](../AGENTS.md)
- [ ] Route handlers stayed thin (validate → service → response)
- [ ] No secrets, `.env`, or large binaries included
- [ ] Docs updated (`docs/API.md` for API changes, `AGENTS.md` CHANGE MAP for
      new modules, `docs/*` for pipeline changes)
- [ ] CHANGELOG updated under **Unreleased** (user-visible changes)
- [ ] PR title is clear and imperative
