# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Professional UI redesign for `/` and `/scan-pdf`: mesh background, glass header with nav, hero + trust strip, refined upload zone, focus-visible rings, `prefers-reduced-motion` support.
- **Scan PDF** button on `/` now navigates to `/scan-pdf` (on-device path); server SSE PDF flow remains available via drag-and-drop.
- `ui-ux-review` design skill (user-level) encoding 2026 web UI/UX best practices.

### Changed

- Buttons, cards, modal, and progress UI aligned to a single design-token system (8px grid, consistent radii, WCAG-oriented contrast).

## [0.2.0] — 2026-09-23

### Added

- On-device full-quality scan page `/scan-pdf` (pdf.js → OpenCV.js worker → pdf-lib) with server-parity output (MAD ≤ 0.05).
- Page-limit picker (10–50 / All) on both scan pages; local caps 250 MB / 250 pages.
- `/api/health` liveness probe; one-click Vercel deploy (`vercel.json`).
- `bun run parity` harness (worker, geometry, full) and `bun run check` vendor gate.

### Changed

- Uniform A4 output pages with thin black frame; smaller PDFs via quality/scale defaults.
- README rewrite; upstream `pdf.worker.js` (never rebundled).
- `vercel.json`: dropped `functions` block (conflicts with `builds`); Hobby defaults apply.

### Fixed

- EXIF orientation on phone photos (`Pillow` `exif_transpose` with `imdecode` fallback).
- `vercel.json` build/route conflict.

## [0.1.0] — 2026-09-14

### Added

- Initial web product: Flask routes, image scan API, server PDF scan with SSE progress, web UI.
- Tier-1 scan pipeline integration (`auto_scan.py`) and reference-quality gate.

[Unreleased]: https://github.com/minhazexo/cam-clone/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/minhazexo/cam-clone/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/minhazexo/cam-clone/releases/tag/v0.1.0
