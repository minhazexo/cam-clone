# Scan Pipeline Deep Dive — `auto_scan.py` + `scan.py` + `scan_pdf.py` + `quality_gate.py`

Main entry: `scan_photo_to_reference(image, ksize, white_point, black_point, black_point2, trim=True, reframe=True, output_scale=2.0, ref_aspect=REF_ASPECT)` (`auto_scan.py:976-988`).

## 1. Geometry stage (first)
Order in code (`auto_scan.py:991-1036`):
1. `align_to_reference_template(image)` (`:568`) — SIFT/RANSAC align to `reference.png` when available. If aligned → skip all trapezoid logic (template path).
2. Else `find_document_contour(working, min_area_ratio=0.25)` (`:51`) + `order_points` (`:38`) + `warp_to_rectangle` (`:81`) — classic 4-point perspective warp.
3. Else `dewarp_by_rulings(working, n_bands=6)` (`:187`) — curl-aware band-by-band y-remap using ruling lines. Helpers: `_probe_gray` (`:98`), `_adaptive_ink_mask` (`:114`), `_ruling_segments(max_tilt 12°)` (`:127`), `_fit_line` (`:177`).
4. Else `rectify_from_rulings(max_tilt 12°)` (`:265`) — trapezoid from rulings.
5. Else `deskew(angle)` (`:352`) via `estimate_skew_angle(max 15°)` (`:324`), plus `residual_deskew(tol 0.25°)` (`:367`) after enhancement.
6. Cleanup (non-template path): `cut_dark_edge_bands(l=0.25,r=0.13)` (`:474`), `trim_white_fill_bands(thr 240, frac 8%)` (`:398`), `trim_smeared_top_band(frac 6%)` (`:428`), `auto_trim_margins(l 0.8%,r 2%,t 1%,b 2%)` (`:867`).

Binding/artifact removers (used in reframe): `remove_binding_rings(zone 0.78, dark 70)` (`:617`), `whiten_corner_smears` (`:663`), `whiten_border_artifacts` (`:695`), `reframe_like_reference` (`:727`), `trim_coil_margin` (`:818`).

Reference helpers: `measure_reference_size/aspect` (`:524,543`), `edge_darkness_profile` (`:452`).

## 2. Photometry stage (second)
`enhance_reference_look(image, ksize=101, white_point, black_point, black_point2, saturate)` (`auto_scan.py:942-969`):
- `high_pass_flatten(ksize)` (`:892`, kernel via `_odd_kernel(min_dim, divisor, 21..101)` at `:884`) — box-blur background subtract, mirrors legacy `highPassFilter(kSize)` in `scan.py:23`.
- Optional saturation boost on BGR (keeps blue headings colored).
- `THRESH_TRUNC` at white point → stretch `×255/wp`; double black stretch `(out-bp)×255/(255-bp)` twice; `THRESH_TOZERO`.
- Per-channel (BGR) so color preserved (docstring `:944-951`).
- Template-aligned path adds unsharp: `GaussianBlur σ0.8`, `addWeighted(1.9, -0.9)` (`:1044-1045`).
- Tunables: `high_pass_flatten`, `white_point_stretch(DEFAULT_WHITE_POINT)` (`:907`), `black_point_stretch` (`:916`), `auto_black_point(pct 8%)` (`:929`).

Legacy equivalent `scan_image(mode)` (`scan.py:120-161`): GCMODE = flatten+white/black color; RMODE = contrast only; SMODE = RMODE + LAB `add(sub(l,b),sub(l,a))` B&W (`blackAndWhite` at `:101`).

## 3. Reframe stage (last, `auto_scan.py:1046-1103`)
- `residual_deskew` if not template-aligned.
- Border/corner whitening **after** reframe (comment `:1053-1058` warns pre-reframe whitening erases bottom ~16% on full-frame photos).
- `reframe_like_reference` locks canvas aspect to `ref_aspect`, `output_scale=2.0` upscales to reference resolution.
- Never raises on degenerate input; photometry-only fallback.

## 4. PDF wrapper (`scan_pdf.py`)
- `_pixmap_to_bgr` (`:49`): handles CMYK (invert), RGB→BGR, gray→BGR.
- `iter_pdf_pages_as_bgr(pdf, dpi=300)` (`:66`): `zoom=dpi/72`, `get_pixmap(matrix, alpha=False)`.
- `iter_images_as_bgr` / `collect_pages` (`:81,104`): PDF / single image / dir sorted.
- `save_bgr_pages_as_pdf(pages, out, quality=90)` (`:120`): temp JPEGs → `new_page(w,h)` + `insert_image(Rect)`, `save(garbage=4, deflate=True)`.
- `scan_pdf_to_reference(in, out, dpi, images_out, quality, no_trim, page_limit, **scan_kwargs)` (`:154-193`): loads, slices limit, per-page scan with timing logs, optional `page_####.jpg` dump, saves PDF, prints `done: N page(s)`.
- CLI (`:196-228`): `--dpi 300 --images-out --jpeg-quality 90 --no-trim --no-reframe --output-scale 2.0 --white-point --black-point`.

## 5. Quality gate (`quality_gate.py:1-194`)
Anchored to `reference.png` itself (both downscaled to 480px via `downscale_to_width`):
- `stats()`: gray_mean/std, ink_mean (<200), vd_90 (<90%), dark_128, chroma99.
- `ssim_gray()` (11×11 σ1.5), `shared_roi_stats(align=True)`: ECC affine fit, ink-mask ROI, PSNR/SSIM/MAD.
- `ink_bbox(thresh 100)` normalized bbox.
- Checks: photometry anchored ±(5, 12, 15, 2.0, 2.5, 20); PSNR 8-100, SSIM 0.32-1, MAD 0-55; tilt ±0.35°; edge dark% 0-0.5%; margins vs ref bbox. Prints PASS/FAIL + `ALL PASS`. Needs `Work Images/pdf photo..jpg` + `reference.png` (absent here).
