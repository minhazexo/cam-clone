# Scan pipeline

The scanner turns a photo of a page (BGR image or RGBA canvas) into a clean,
flat, white-background scan. The same algorithm exists twice:

| Stage | Python | JavaScript (browser) |
|---|---|---|
| orchestration | `rscan/scanner/pipeline.py` | `processPage` in `static/js/workers/scan-worker-v2.js` |
| geometry | `rscan/scanner/geometry.py` | `static/js/workers/scan-geometry.js` |
| probe/masks | `rscan/scanner/preprocessing.py` | `probeGray` / `adaptiveInkMask` |
| photometry | `rscan/scanner/photometry.py` | `enhanceReferenceLook` |
| cleanup | `rscan/scanner/postprocessing.py` | trims/reframe/whiten functions |
| constants | `rscan/scanner/constants.py` | top of `scan-worker-v2.js` + `scan-geometry.js` |

Parity between the two is protected by `tests/parity/*` (see `TESTING.md`).

## Stage order

`scan_photo_to_reference(image, output_scale=2.0, reframe=True, trim=True)`

1. **Template alignment (guarded).** If the bundled reference scan is present
   *and* SIFT matches strongly, warp to the reference canvas. This is a
   calibration path for the reference fixture; normal uploads skip it.
2. **Geometry** (one of, in this priority):
   * `find_document_contour` + `warp_to_rectangle` — a closed 4-point page quad
     exists (photo of a page on a desk);
   * `dewarp_by_rulings` — band-wise y-remap that flattens *curved* pages
     (notebook photographed up close); returns `None` when evidence is thin;
   * `rectify_from_rulings` — trapezoid→rectangle keystone correction from the
     top/bottom ruling lines;
   * `deskew` — plain rotation, using text lines or colored rulings.
3. **Pre-enhancement trims** (raw photo: shadows are still dark and separable)
   * `cut_dark_edge_bands` — removes the page-gap shadow on the **left only**
     (a right cut eats real content; see the comment in the code);
   * `trim_white_fill_bands` — drops warp-fill borders, capped per side;
   * `trim_smeared_top_band` — drops blurry extrapolated strips;
   * `auto_trim_margins` — micro trim of ink-free outer rows/columns.
4. **Photometry** (`enhance_reference_look`)
   * `high_pass_flatten` — `img − box_blur(img) + 127`, per channel;
   * saturation boost (default 1.25) around luminance, preserving colored ink;
   * white-point stretch — truncate above 127, stretch `[0,127] → [0,255]`;
   * black-point stretch — `(img − 66) · 255/(255−66)`, then the same with 20;
   * `THRESH_TOZERO` to clear negatives.
5. **Reframe + cleanup** (enhanced image: paper is white, artifacts obvious)
   * `reframe_like_reference` (reference margins) — ink bounding box centred on
     a white canvas with the reference aspect ratio;
   * `remove_binding_rings` — thickness + diagonal signature inpaint of spiral
     binding (runs on the *unrotated* canvas so ring cores stay thick);
   * `residual_deskew` — re-measures tilt now that rulings are visible;
   * `auto_trim_margins(top=0.12)` — post-enhancement desk/shadow trim;
   * second `reframe_like_reference` with halved margins → clean white edges;
   * `whiten_corner_smears`, `whiten_border_artifacts`;
   * light unsharp (`sigma 0.8`, 1.3/−0.3), or the 2.0× Lanczos + unsharp when
     `output_scale=2.0` (the reference is ~2× the source pixels);
   * final size fit to the reference dimensions (or reference aspect).

`preserve_borders=True` skips every destructive cleanup (coils, notes and
watermarks survive) while still straightening, enhancing and framing.

## Constants and why they matter

| Constant | Value | Purpose | Parity-sensitive |
|---|---|---|---|
| `DEFAULT_WHITE_POINT` | 127 | highlights → white | yes |
| `DEFAULT_BLACK_POINT` | 66 | first ink stretch | yes |
| `DEFAULT_BLACK_POINT2` | 20 | second ink stretch | yes |
| `DEFAULT_SATURATE` | 1.25 | keep colored ink alive | yes |
| `DEFAULT_KSIZE_DIVISOR` | 8 | flatten kernel = `min(h,w)//8` (odd, 21…101) | yes |
| `REF_MARGIN_*` | 0.069 / 0.071 / 0.070 / 0.040 | reference framing | yes |
| `REF_ASPECT_FALLBACK` | 893/1263 | canvas aspect without the reference asset | yes |
| `DEFAULT_OUTPUT_SCALE` | 2.0 | image scan upscale (PDF scans pass 1.0) | yes |

Changing any of these requires mirroring the value in the JS worker and
re-running `bun run parity`. The gate is `MAD ≤ 3.0` on 8-bit pixels plus exact
output dimensions; a real algorithmic drift shows up as a much larger number,
so a failing gate means "investigate", never "raise the threshold".

## Worker protocol

The browser runs the pipeline inside `static/js/workers/scan-worker-v2.js`
(loaded by `scan-worker.js` as a fallback). Classic worker: no ES modules, so
shared code is pulled in with `importScripts` (OpenCV.js, then
`scan-geometry.js`).

### Messages

```jsonc
// 1. warm-up probe (sent by engine-loader.js)
{ "ping": true }
// → { "ready": true, "engine": "v2-full" }

// 2. scan request (main thread → worker), RGBA, 4 bytes/px
{ "width": 1200, "height": 1700, "pixels": ArrayBuffer }   // transferred
// → success
{ "width": 1180, "height": 1670, "pixels": ArrayBuffer,     // transferred
  "stats": { "sharpness": 2081.6 } }
// → failure
{ "error": "processPage: expected 8160000 bytes, got 0" }
```

Rules that keep it correct and fast:

* `pixels` is **transferred**, not copied; the sender's `ArrayBuffer` is
  detached afterwards, so the canvas is the only owner of the pixels.
* Every `cv.Mat` is deleted in a `try/finally` inside the worker. One leaked
  Mat per page crashes the tab on long PDFs.
* The worker replies with an explicit `error` message instead of throwing, so
  the UI can show a message instead of dying silently.
* The warm worker is reused for every page of every scan
  (`engine-loader.js`); only the fallback worker is terminated per scan.
* Node parity harnesses load the same file through `require()`
  (`module.exports = { processPage, processImage, … }`), so the worker cannot
  use browser-only APIs at module scope.

### Lifecycle

```
engine-loader.ensure()
  ├─ new Worker(scan-worker-v2.js); post {ping:true}
  │    └─ ready → hand the warm worker to the caller (never terminated)
  └─ on failure → new Worker(scan-worker.js); post a 4x4 dummy image
       └─ response → "fallback" source (lower quality; /scan-pdf waits for v2)
shutdownEngine()  ← window `pagehide` on the on-device page
```

## Node parity harnesses

| Harness | Covers | Gate |
|---|---|---|
| `tests/parity/parity_worker.js` | photometry (`processImage`) | MAD ≤ 3.0, sharpness ±10 % |
| `tests/parity/parity_geometry.js` | geometry + cleanup stages | dims exact, MAD ≤ 3.0 (≤ 1.0 for non-rotating stages) |
| `tests/parity/parity_full.js` | full pipeline (`processPage`) | dims exact, MAD ≤ 3.0, tilt/sharpness |

Expected bytes come from `tests/fixtures/*.rgb`, generated by
`scripts/gen_fixtures.py` / `scripts/dump_stages.py` from the Python pipeline.
Regenerate them only with an intentional pipeline change, and explain the delta.
