# Graph Report - DocumentScanner-main  (2026-09-12)

## Corpus Check
- 18 files · ~79,533 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 186 nodes · 264 edges · 26 communities (17 shown, 9 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 13 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Deskew and Ruling Line Dewarping
- Java OpenCV Scan Module
- Multi-Page PDF Processing Pipeline
- Flask Web API Service
- Auto Scan and Reference Enhancement
- Architecture and Core Dependencies
- Margin Trimming and Geometry Cleaning
- Python Core Image Filter Pipeline
- Node.js OpenCV Scanner
- Quality Gate and Image Metrics
- Web UI Client Application
- Reference Golden Sample Document
- Sample Document 4ef127670c6f Extraction
- Scanner Margin Crop Tests
- Handwritten Sample b2b927482660 Extraction
- Edge Shadow and Coil Band Removal
- Document Contour Detection
- Raw Document Photo Analysis
- Histogram Black Point Calibration
- Black Point Contrast Stretching
- Warp Fill Band Trimming
- Border Artifact Whitening
- Reference Style Page Reframing
- Coil Margin Filtering
- Scanned Page Sample Analysis
- Numerical Computing Dependency

## God Nodes (most connected - your core abstractions)
1. `scan_photo_to_reference()` - 26 edges
2. `Scan` - 10 edges
3. `estimate_skew_angle()` - 8 edges
4. `dewarp_by_rulings()` - 7 edges
5. `main()` - 7 edges
6. `scan_pdf_to_reference()` - 7 edges
7. `_ruling_segments()` - 6 edges
8. `rectify_from_rulings()` - 6 edges
9. `residual_deskew()` - 6 edges
10. `DocumentScanner RScan Overview` - 6 edges

## Surprising Connections (you probably didn't know these)
- `api_scan()` --calls--> `scan_photo_to_reference()`  [INFERRED]
  app.py → RScan/Python/scan/auto_scan.py
- `api_scan_pdf()` --calls--> `scan_pdf_to_reference()`  [INFERRED]
  app.py → RScan/Python/scan/scan_pdf.py
- `RScan Web UI Template` --conceptually_related_to--> `Flask Web Framework Dependency`  [INFERRED]
  templates/index.html → requirements.txt
- `DocumentScanner RScan Overview` --references--> `OpenCV Computer Vision Dependency`  [EXTRACTED]
  README.md → requirements.txt
- `RScan Web UI Template` --conceptually_related_to--> `DocumentScanner RScan Overview`  [INFERRED]
  templates/index.html → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Document Scanning Web UI Workflow** — templates_index_upload_section, templates_index_processing_section, templates_index_results_section [EXTRACTED 1.00]
- **RScan Core Python Dependencies** — requirements_flask, requirements_opencv_python, requirements_numpy, requirements_pymupdf [EXTRACTED 1.00]

## Communities (26 total, 9 thin omitted)

### Community 0 - "Deskew and Ruling Line Dewarping"
Cohesion: 0.14
Nodes (18): _adaptive_ink_mask(), deskew(), dewarp_by_rulings(), estimate_skew_angle(), _fit_line(), _probe_gray(), Ink/lines mask robust to uneven lighting (adaptive, inverted)., Long near-horizontal ruling-line segments in probe coords. Filters out the… (+10 more)

### Community 1 - "Java OpenCV Scan Module"
Cohesion: 0.19
Nodes (8): Mat, org.opencv.core.Mat, Main, Scan, ScanMode, GCMODE, RMODE, SMODE

### Community 2 - "Multi-Page PDF Processing Pipeline"
Cohesion: 0.19
Nodes (14): collect_pages(), iter_images_as_bgr(), iter_pdf_pages_as_bgr(), main(), _pixmap_to_bgr(), Scan PDF photos to reference quality. Feature: convert every page-photo of an…, Write BGR pages to a PDF, one page per image, original pixel sizes., Scan ``input_path`` (PDF / image / dir) to reference quality. Returns the… (+6 more)

### Community 3 - "Flask Web API Service"
Cohesion: 0.22
Nodes (12): _allowed(), api_image(), api_pdf(), api_scan(), api_scan_pdf(), index(), RScan Web — CamScanner-style document scanner website. Run: pip install -r…, Serve a scanned image by its ID. (+4 more)

### Community 4 - "Auto Scan and Reference Enhancement"
Cohesion: 0.18
Nodes (12): enhance_reference_look(), high_pass_flatten(), measure_reference_aspect(), _odd_kernel(), Reference-quality photo scanner. Converts phone photos of documents (including…, # NOTE: slope is scale-invariant (dy/dx); center in full-res coords., Return reference.png's canvas aspect ratio (width / height). Measures the full…, Flatten uneven lighting: img - background + 127, per channel. (+4 more)

### Community 5 - "Architecture and Core Dependencies"
Cohesion: 0.17
Nodes (12): Automatic Document Cropping Concept, DocumentScanner RScan Overview, Java Scan Module Reference, Parameter Selection Automation Goal, Python Scan Module Reference, Flask Web Framework Dependency, OpenCV Computer Vision Dependency, PyMuPDF PDF Processing Dependency (+4 more)

### Community 6 - "Margin Trimming and Geometry Cleaning"
Cohesion: 0.17
Nodes (12): auto_trim_margins(), Cut a warp-smeared band at the top edge, if present. Perspective extrapolation…, Erase spiral-binding rings overlapping the page (inpaint with paper). Rings are…, Whiten out-of-focus neighbor-page smears in the corners. On the enhanced image…, Micro-border trim. Heavy lifting (shadow/coil) is done adaptively by…, Perspective-warp the quad ``corners`` to a top-down rectangle., Convert one phone photo (BGR) to reference-quality scan (BGR). Geometry first…, remove_binding_rings() (+4 more)

### Community 7 - "Python Core Image Filter Pipeline"
Cohesion: 0.20
Nodes (6): _map_array(), Stateless version of map() for the functional API below., Scan a BGR image without globals (functional equivalent of this module). Modes:…, Reference-quality scan with geometry fix (see auto_scan.py). Falls back to…, scan_image(), scan_photo_auto()

### Community 8 - "Node.js OpenCV Scanner"
Cohesion: 0.29
Nodes (8): anchor, blackAndWhite(), blackPointSelect(), cv, highPassFilter(), Jimp, scanImage(), whitePointSelect()

### Community 9 - "Quality Gate and Image Metrics"
Cohesion: 0.31
Nodes (9): downscale_to_width(), ink_bbox(), main(), Quality gate: compare pipeline output on 1.jpg against reference.jpg. The gate…, Reference-anchored statistics measured on the given image., PSNR / SSIM / MAD on the region where both images contain ink. Both inputs must…, shared_roi_stats(), ssim_gray() (+1 more)

### Community 10 - "Web UI Client Application"
Cohesion: 0.52
Nodes (5): esc(), handleFiles(), showImageResults(), showPdfResult(), showUpload()

### Community 11 - "Reference Golden Sample Document"
Cohesion: 0.53
Nodes (6): Canonical Ensemble Comparison Column, Reference Document Golden Sample (Bengali Physics Note), Grand Canonical Ensemble Comparison Column, Microcanonical Ensemble Comparison Column, Ensemble Partition Function Formulations, Ensemble Probability Distribution Formulations

### Community 12 - "Sample Document 4ef127670c6f Extraction"
Cohesion: 0.40
Nodes (5): Canonical Ensemble, Document Sample (4ef127670c6f.jpg), Grand Canonical Ensemble, Microcanonical Ensemble, Statistical Mechanics Ensembles Comparison Table

### Community 14 - "Handwritten Sample b2b927482660 Extraction"
Cohesion: 0.83
Nodes (4): Canonical Ensemble Comparison Column, Handwritten Statistical Physics Notes (b2b927482660.jpg), Grand Canonical Ensemble Comparison Column, Microcanonical Ensemble Comparison Column

### Community 15 - "Edge Shadow and Coil Band Removal"
Cohesion: 0.50
Nodes (4): cut_dark_edge_bands(), edge_darkness_profile(), Per-column dark fraction, maxed over sliding row windows. Averaging over the…, Cut page-gap shadow (left) and spiral-coil band (right) adaptively. Operates on…

### Community 16 - "Document Contour Detection"
Cohesion: 0.50
Nodes (4): find_document_contour(), order_points(), Order 4 points as (top-left, top-right, bottom-right, bottom-left)., Find the largest plausible 4-point document contour, or None. Returns ordered…

### Community 17 - "Raw Document Photo Analysis"
Cohesion: 0.83
Nodes (4): Canonical Ensemble (Handwritten Notes), Grand Canonical Ensemble (Handwritten Notes), Microcanonical Ensemble (Handwritten Notes), Raw Document Photo - Statistical Mechanics Ensembles Comparison

## Knowledge Gaps
- **22 isolated node(s):** `GCMODE`, `RMODE`, `SMODE`, `Jimp`, `cv` (+17 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 80 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `scan_photo_to_reference()` connect `Margin Trimming and Geometry Cleaning` to `Deskew and Ruling Line Dewarping`, `Multi-Page PDF Processing Pipeline`, `Flask Web API Service`, `Auto Scan and Reference Enhancement`, `Python Core Image Filter Pipeline`, `Quality Gate and Image Metrics`, `Scanner Margin Crop Tests`, `Edge Shadow and Coil Band Removal`, `Document Contour Detection`, `Warp Fill Band Trimming`, `Border Artifact Whitening`, `Reference Style Page Reframing`?**
  _High betweenness centrality (0.161) - this node is a cross-community bridge._
- **Why does `scan_pdf_to_reference()` connect `Multi-Page PDF Processing Pipeline` to `Flask Web API Service`, `Margin Trimming and Geometry Cleaning`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Why does `api_scan()` connect `Flask Web API Service` to `Margin Trimming and Geometry Cleaning`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **What connects `GCMODE`, `RMODE`, `SMODE` to the rest of the system?**
  _22 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Deskew and Ruling Line Dewarping` be split into smaller, more focused modules?**
  _Cohesion score 0.1437908496732026 - nodes in this community are weakly interconnected._