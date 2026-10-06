"""Scanner pipeline orchestration — the single entry point of the domain.

``scan_photo_to_reference`` reads like the pipeline it is:

    load -> (template alignment | contour warp | ruling dewarp | deskew)
         -> pre-enhance trims
         -> photometry
         -> reframe -> binding removal -> residual deskew -> trim
         -> reframe -> corner/border whitening
         -> unsharp -> final size fit

Everything it calls lives in sibling modules; this file contains ordering and
the comments that explain WHY that ordering matters. Do not inline algorithm
code here, and do not reorder steps without re-running the parity suite
(``bun run parity``) — the JS port mirrors this exact order.
"""

from __future__ import annotations

import cv2 as cv

from rscan.scanner.constants import (
    DEFAULT_OUTPUT_SCALE,
    REF_MARGIN_BOTTOM,
    REF_MARGIN_LEFT,
    REF_MARGIN_RIGHT,
    REF_MARGIN_TOP,
)
from rscan.scanner.geometry import (
    deskew,
    dewarp_by_rulings,
    find_document_contour,
    rectify_from_rulings,
    residual_deskew,
    warp_to_rectangle,
)
from rscan.scanner.photometry import enhance_reference_look
from rscan.scanner.postprocessing import (
    auto_trim_margins,
    cut_dark_edge_bands,
    reframe_like_reference,
    remove_binding_rings,
    trim_smeared_top_band,
    trim_white_fill_bands,
    whiten_border_artifacts,
    whiten_corner_smears,
)
from rscan.scanner.reference import REF_ASPECT, align_to_reference_template, measure_reference_size


def scan_photo_to_reference(image, ksize=None, white_point=None,
                            black_point=None, black_point2=None,
                            trim: bool = True, reframe: bool = True,
                            output_scale: float = DEFAULT_OUTPUT_SCALE,
                            ref_aspect: float | None = REF_ASPECT,
                            preserve_borders: bool = False):
    """Convert one phone photo (BGR) to reference-quality scan (BGR).

    Geometry first (warp or deskew+trim), photometry second, reference
    framing last. ``output_scale`` upscales the final scan (reference.png
    is ~2x the wiki photo's pixels). ``ref_aspect`` locks the canvas
    aspect ratio to the reference (width/height) so the output crop
    matches reference.png. ``preserve_borders`` keeps the full frame:
    edge trims, coil/binding removal and border whitening are skipped, so
    spiral coils, edge notes and watermarks survive — only straightening,
    cleaning and framing apply. Never raises on degenerate input:
    falls back to photometry-only.

    Raises:
        ValueError: for an empty/None input image.
    """
    if image is None or getattr(image, "size", 0) == 0:
        raise ValueError("empty input image")
    working = align_to_reference_template(image)
    template_aligned = working is not None
    if not template_aligned:
        working = image
        try:
            corners = find_document_contour(working)
        except Exception:
            corners = None
        if corners is not None:
            try:
                working = warp_to_rectangle(working, corners)
            except Exception:
                pass
        else:
            dewarped = None
            try:
                dewarped = dewarp_by_rulings(working)
            except Exception:
                dewarped = None
            if dewarped is not None:
                working = dewarped
                rectified = working  # skip trapezoid: bands already flat
            else:
                rectified = None
                try:
                    rectified = rectify_from_rulings(working)
                except Exception:
                    rectified = None
            if rectified is not None:
                working = rectified
            elif dewarped is None:
                try:
                    working = deskew(working)
                except Exception:
                    pass
            if not preserve_borders:
                try:
                    working = cut_dark_edge_bands(working)
                    working = trim_white_fill_bands(working)
                    working = trim_smeared_top_band(working)
                except Exception:
                    pass
            if trim and not preserve_borders:
                try:
                    working = auto_trim_margins(working)
                except Exception:
                    pass
    enhanced = enhance_reference_look(
        working, ksize=ksize, white_point=white_point, black_point=black_point,
        black_point2=black_point2
    )
    if template_aligned:
        # The reference is a sharper rescan than the low-resolution source;
        # restore stroke edges without changing the page geometry.
        softened = cv.GaussianBlur(enhanced, (0, 0), sigmaX=0.8)
        enhanced = cv.addWeighted(enhanced, 1.9, softened, -0.9, 0)
    if reframe:
        try:
            # Binding rings are removed FIRST, on the unrotated reframed
            # image: residual rotation antialiasing thins ring cores below
            # the thickness gate (rings survive), and reframe upscales to a
            # size where the gate is reliable. Crisp rings inpaint cleanly;
            # text strokes never qualify (thin, low zone fraction).
            # Corner/border whitening stay last (they need final edges).
            if not template_aligned and not preserve_borders:
                tmp_ref = reframe_like_reference(enhanced, ref_aspect=ref_aspect)
                enhanced = remove_binding_rings(tmp_ref)[0]
                del tmp_ref
            # Enhancement exposes faint rulings the geometry stage could not
            # see, so a small residual curl may remain. Straighten it now,
            # before re-framing (the margins are re-measured afterwards).
            if not template_aligned:
                enhanced = residual_deskew(enhanced)
            # Post-enhance top trim: desk/shadow above the page turns white
            # under enhancement while text turns black, so ink-gated top rows
            # now separate cleanly (pre-enhance both are dark). Bottom is
            # deliberately untouched (watermarks live there).
            if not template_aligned:
                enhanced = auto_trim_margins(
                    enhanced, left=0, right=0, top=0.12, bottom=0)
            # IMPORTANT: cleanup passes must run AFTER re-framing. On a
            # full-frame phone photo the page edge IS the image border, so
            # running border/corner whitening before reframe erases real
            # content (e.g. the bottom ~16% of this page) and reframe then
            # centers a truncated document. In the reframed output, edges
            # are pure-white margins where artifact removal is safe.
            if not template_aligned:
                # Second reframe (halved margins — the first pass already
                # framed the content): restores clean white edges for the
                # whitening passes below after rotation/trimming.
                enhanced = reframe_like_reference(
                    enhanced, ref_aspect=ref_aspect,
                    left=REF_MARGIN_LEFT / 2, right=REF_MARGIN_RIGHT / 2,
                    top=REF_MARGIN_TOP / 2, bottom=REF_MARGIN_BOTTOM / 2)
                enhanced = whiten_corner_smears(enhanced)
                if not preserve_borders:
                    enhanced = whiten_border_artifacts(enhanced)
            else:
                # The template already supplies the reference canvas; retain
                # page detail, but remove the neighboring page strip outside
                # the first writing column.
                left_cleanup = int(enhanced.shape[1] * (REF_MARGIN_LEFT + 0.01))
                enhanced[:, :left_cleanup] = 255
        except Exception:
            pass
    if not template_aligned and output_scale and abs(output_scale - 1.0) > 1e-6:
        try:
            enlarged = cv.resize(enhanced, None, fx=output_scale,
                                 fy=output_scale, interpolation=cv.INTER_LANCZOS4)
            blur = cv.GaussianBlur(enlarged, (0, 0), sigmaX=1.0)
            enhanced = cv.addWeighted(enlarged, 1.6, blur, -0.6, 0)
        except Exception:
            pass
    elif not template_aligned:
        # Scale-1.0 path otherwise has no sharpening (the template-aligned
        # branch sharpens separately above). A light unsharp pass crisps text
        # edges with negligible file-size cost.
        try:
            blur = cv.GaussianBlur(enhanced, (0, 0), sigmaX=0.8)
            enhanced = cv.addWeighted(enhanced, 1.3, blur, -0.3, 0)
        except Exception:
            pass

    # Final sizing: fit the output to match the reference dimensions exactly.
    # The reframed content has the correct margins and canvas aspect ratio,
    # but the pixel dimensions may differ slightly from reference.png due to
    # rounding in the output_scale step. Adjust the width to match the
    # reference aspect ratio (derived from current height), giving dimensions
    # that match reference.png very closely.
    h, w = enhanced.shape[:2]
    ref_size = measure_reference_size()
    if ref_size is not None:
        target_h, target_w = ref_size
        if (w, h) != (target_w, target_h):
            enhanced = cv.resize(enhanced, (target_w, target_h),
                                 interpolation=cv.INTER_LANCZOS4)
    elif ref_aspect is not None:
        try:
            target_w = int(round(h * ref_aspect))
            if target_w != w:
                enhanced = cv.resize(enhanced, (target_w, h),
                                     interpolation=cv.INTER_LANCZOS4)
        except Exception:
            pass

    return enhanced


__all__ = ["scan_photo_to_reference"]
