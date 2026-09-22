# Local Full-Quality Plan — opencv.js port of the scan pipeline

Goal: `/scan-pdf` page opens → scan engine (WASM) downloads in background → user scans PDFs of ANY size locally with Python-pipeline quality. No server, no size cap.

## 1. Deep-dive findings

### 1.1 Function catalog (`RScan/Python/scan/auto_scan.py`, ~1160 lines)
| Group | Functions | Notes for port |
|---|---|---|
| Points/contour | `order_points`, `find_document_contour`, `warp_to_rectangle` | Pure geometry + `findContours/approxPolyDP/getPerspectiveTransform/warpPerspective` — direct port |
| Ruling analysis | `_probe_gray`, `_adaptive_ink_mask`, `_ruling_segments`, `_fit_line` | Morph ops + `HoughLinesP`; `polyfit` → 20-line manual least squares |
| Dewarp/rectify | `dewarp_by_rulings`, `rectify_from_rulings` | `remap` + `getPerspectiveTransform`; NumPy map math → Float32Array loops |
| Deskew | `estimate_skew_angle`, **`estimate_color_ruling_tilt`**, `deskew`, `residual_deskew` | Includes our pink-ruling fix — port as-is (pure Hough) |
| Edge/margin trims | `trim_white_fill_bands`, `trim_smeared_top_band`, `edge_darkness_profile`, `cut_dark_edge_bands`, `auto_trim_margins`, `trim_coil_margin` | Sobel/profile loops + `connectedComponentsWithStats` |
| Reference/template | `measure_reference_size/aspect`, `align_to_reference_template`, `reframe_like_reference` | **SIFT path SKIPPED** (no reference.png, see 1.2); reframe math ports directly |
| Cleanup | `remove_binding_rings`, `whiten_corner_smears` (`floodFill`), `whiten_border_artifacts` | Direct port |
| Photometry | `_odd_kernel`, `high_pass_flatten`, `white_point_stretch`, `black_point_stretch`, `auto_black_point`, `enhance_reference_look`, `scan_photo_to_reference` | Core of Phase 1; `filter2D`+ones → `cv.blur` (identical box math, separable=faster); `percentile` → sort-based |
| Border (scan_pdf.py) | `draw_page_border` | Trivial `rectangle` — or canvas 2D, no cv needed |

### 1.2 opencv.js 4.8.0 API verdict — verified BY EXECUTION in Node (not docs)
`static/vendor/opencv.js` (9.99 MB, pinned 4.8.0, fallback CDN `docs.opencv.org/4.8.0`, `4.5.5`):
- ✓ ALL pipeline ops: HoughLinesP, warpPerspective, remap, floodFill, **connectedComponentsWithStats**, GaussianBlur, Canny, getPerspectiveTransform, warpAffine, adaptiveThreshold, morphologyEx, filter2D, addWeighted, findContours, approxPolyDP, connectedComponents, goodFeaturesToTrack, BFMatcher, findTransformECC (parity tests!)
- ✗ `SIFT_create` MISSING → template/SIFT path skipped in browser; `template_aligned=false` always (matches current reality: no reference.png anyway)

### 1.3 Data-flow mapping (browser)
```
pdf.js render (RGBA canvas, scale=200/72, cap 2500px wide)
 → worker: strip alpha → RGB Mat → pipeline (RGB, same constants as Python)
 → add opaque alpha → transferable buffer → main thread putImageData
 → canvas.toDataURL(jpeg, 0.80) → pdf-lib embedJpg → A4 page, aspect-fit, margin 0
 → black frame via canvas strokeRect (no cv needed) → blob download
```
- Resolution parity: server renders 200 DPI; browser `scale = 200/72 ≈ 2.78` (cap 2500px; mobile cap 1800px for memory).
- JPEG parity: q80 (server q78 — visually identical band).
- RGB vs BGR: channel order handled once at conversion boundaries; all pipeline math is channel-symmetric except R−G ruling (map to R−G on RGB side).
- Numeric parity: JS numbers are float64 (same as NumPy float64); cv maps stay float32 like Python. Box blur via `cv.blur` == `filter2D(ones/N)` bit-closest enough (MAD target ≤3.0 on fixtures).
- Mat lifecycle: every `new cv.Mat` / op result `.delete()`d in try/finally per page — leak = tab crash on 50+ pages. Lint rule: no bare `new cv.Mat` outside helpers that delete.

### 1.4 What is NOT ported
- SIFT template alignment (missing in WASM + no reference asset).
- `quality_gate.py` (stays Python; but `findTransformECC` exists so a JS parity metric is possible later).
- Server SSE/threading (irrelevant locally; existing page-by-page worker loop reused).

## 2. Steps (one by one, each merged + tested)

- [x] **Step 1 — shell + engine delivery + fixtures (DONE, verified):** `/scan-pdf` → 200 with all section IDs + loader tags; `node --check` clean; `bun run scripts/check.ts` passes incl. `opencv.js`; fixtures + baselines in §3; Node API smoke test passed (all ops OK, SIFT missing as expected).
- [x] **Step 2 — photometry worker (DONE):** `scan-worker-v2.js` + `tests/parity_worker.js` ALL PASS (MAD 0.003, sharp ±0.03%).
- [x] **Step 3 — geometry (DONE):** `scan-geometry.js` (all stages incl. pink fix, SIFT stubbed) + `tests/parity_geometry.js` ALL PASS (geom MAD 0.06, reframe/cleanups 0.000 bit-exact, residual no-op verified). Notable find: Python `int()` truncates but `round()` is banker's — port has `pyInt`/`pyRound` helpers; this fixed a 1px paste offset.
- [x] **Step 4 — assembly + page (DONE):** `scanpdf.js` (200-DPI render cap 2500/1800, q0.80 embed, orientation-matched A4, canvas border, guards mirrored from app.js, v1-worker fallback) wired into `scan_pdf.html`; Flask + syntax verified.
- [x] **Step 5 — parity + docs (DONE):** `tests/parity_full.js` ALL PASS — full `processPage` vs Python full pipeline: dims exact, MAD 0.04, sharp ±0.1%. Real page (Electricity p0 @200DPI, local-only check): dims exact 1737×2456, MAD 0.054, tilt −1.00 both, sharp 570.2 vs 570.1, 8.5 s/page WASM single-thread (matches estimate). Known artifact: estimator reads −0.89 on Python's own aspect-fit output vs 0.00 on ours at MAD 0.04 — knife-edge Hough noise, gate ±1.0 documents it.

## 3. Baselines (Step 1 fixtures, Python pipeline, synthetic 800×1100 @2° tilt)
Regenerate: `python scripts/gen_fixtures.py` (needs numpy+opencv only, no PDFs).
- `tilt_ruled` (pink ruling): out_tilt=0.00° (pink fix ate the full 2°), sharp 1121→1829, out 808×1143, q80 69,356 B.
- `tilt_plain` (no ruling): out_tilt=-0.89° (luminance path, partial — port must REPLICATE, not beautify), sharp 1110→2125, out 738×1044, q80 53,431 B.
- Parity gate (Steps 2–3): worker output vs `exp_*` → MAD ≤3.0 AND tilt within ±0.15° of these numbers AND sharpness within ±10%.

## 4. Risks & mitigations
| Risk | Mitigation |
|---|---|
| 10 MB WASM first load | Lazy-load on `/scan-pdf` only; browser caches; progress step in UI |
| WASM ~1.5–2× slower than native (≈6–8 s/page @200 DPI) | Page-by-page progress (already in UI); 100 pages ≈ 12 min local — acceptable, still unlimited |
| iOS Safari memory (2500×3500×4 = 35 MB transient) | Mobile cap 1800px wide; per-page Mat cleanup |
| Numeric drift (float32 maps, blur equivalence) | MAD ≤3.0 gate on fixtures per step; eyeball on real pages |
| API gap discovered mid-port | Probe-first rule: every new cv fn must pass the Node smoke test before use |
