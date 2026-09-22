# Graph Report - Cam-Scanner-Clone  (2026-09-22)

## Corpus Check
- 19 files · ~50,336 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3144 nodes · 7911 edges · 125 communities (41 shown, 58 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 774 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Canvas Render Commands
- Text Rendering Ops
- Page Dictionary Access
- Decode Utilities
- Worker Node Factory
- Image Sampling
- Canvas Font Setup
- Annotation Edit UI
- Worker Constructors
- Annotation Storage
- SVG Annotation Layer
- Draw Dimensions
- XML Namespace Nodes
- Worker Messaging
- Range Readers
- Render Layers
- Layout Calculations
- Editor Registration
- HTML Finalize Hooks
- Catalog Conversion
- Print Attributes
- Minified Worker Vars
- Font Decrypt
- Page Cleanup
- Font Resources
- Runtime Constructors
- Viewport Transform
- Form Attachments
- Stream Byte IO
- XRef Decrypt
- Frontend Scan UI
- Optional Content
- Decimal Formatting
- Canvas Path Ops
- Text Extraction
- Glyph Calendar
- Font Fallback
- Form Field Names
- HTML Clean
- PDF Document Proxy
- Password Parsing
- Element Binding
- PDF Objects Fetch
- Worker Transport Layer
- Rotate Operations
- Auto Scan Core
- Pixel Visitor
- Request Cancel
- Flask Scan API
- Reference Template Alignment
- Map Operations
- Font Cache
- PDF Document Loading
- Project Docs UI
- Date Drawing
- Dict Parsing
- Loopback Port
- JS Dependencies Manifest
- Appearance Streams
- Image Ops Queue
- Barcode Tables
- Deskew Quality Gate
- Annotation Creation
- Minified Runtime Utils
- PDF Page Proxy
- PDF Scan Ingest
- Destinations RGB
- Image Paragraph
- Glyph Tables
- Minified Functions
- Dewarp Ruling Lines
- Photo Scan Filters
- Minified Helpers
- Data Range Transport
- Subform Binding
- Encrypt Parsing
- XFA Objects
- Data Events
- Cleanup Passes
- Render Tasks
- Console Parsing
- Page Area
- Whitespace Finalize
- Text Matrix
- Usable Pages
- Platform Support
- Physics Ensemble Notes
- ExData Mode
- Minified Shortcuts
- Render Task
- Build Script TS
- Whitespace Traverse
- Solid Template
- Settled Promises
- Vercel Deploy Config
- Submit URL
- Subject DNs
- Type Check Script
- NumPy Dependency

## God Nodes (most connected - your core abstractions)
1. `X` - 167 edges
2. `S()` - 147 edges
3. `t()` - 147 edges
4. `U` - 136 edges
5. `C` - 134 edges
6. `s()` - 127 edges
7. `O()` - 124 edges
8. `F()` - 122 edges
9. `ht` - 117 edges
10. `e` - 114 edges

## Surprising Connections (you probably didn't know these)
- `api_scan()` --calls--> `scan_photo_to_reference()`  [INFERRED]
  app.py → RScan/Python/scan/auto_scan.py
- `_scan_pdf_worker()` --calls--> `collect_pages()`  [INFERRED]
  app.py → RScan/Python/scan/scan_pdf.py
- `_scan_pdf_worker()` --calls--> `save_bgr_pages_as_pdf()`  [INFERRED]
  app.py → RScan/Python/scan/scan_pdf.py
- `api_scan_pdf()` --calls--> `scan_pdf_to_reference()`  [INFERRED]
  app.py → RScan/Python/scan/scan_pdf.py
- `Flask` --conceptually_related_to--> `RScan Index Page`  [INFERRED]
  requirements.txt → templates/index.html

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Scan workflow from upload through processing to results** — templates_index_upload_section, templates_index_processing_section, templates_index_results_section [EXTRACTED 1.00]
- **Python backend dependency stack** — requirements_flask, requirements_opencv_python, requirements_numpy, requirements_pymupdf [EXTRACTED 1.00]
- **Three Ensembles Compared in Table** — img_20260905_wa0005_microcanonical_ensemble, img_20260905_wa0005_canonical_ensemble, img_20260905_wa0005_grand_canonical_ensemble [INFERRED 0.85]

## Communities (125 total, 58 thin omitted)

### Community 3 - "Decode Utilities"
Cohesion: 0.05
Nodes (21): ce(), D(), K(), oe(), V(), D, ce(), D() (+13 more)

### Community 4 - "Worker Node Factory"
Cohesion: 0.05
Nodes (13): u(), M(), B(), P(), z(), w(), A(), z() (+5 more)

### Community 6 - "Canvas Font Setup"
Cohesion: 0.04
Nodes (3): a(), i(), n()

### Community 7 - "Annotation Edit UI"
Cohesion: 0.05
Nodes (4): bezierCurveTo(), L, lineTo(), moveTo()

### Community 12 - "XML Namespace Nodes"
Cohesion: 0.04
Nodes (3): F(), p(), v()

### Community 14 - "Range Readers"
Cohesion: 0.06
Nodes (22): at(), i(), l(), o(), u(), b(), constructor(), et() (+14 more)

### Community 15 - "Render Layers"
Cohesion: 0.08
Nodes (3): get(), j(), M()

### Community 16 - "Layout Calculations"
Cohesion: 0.04
Nodes (4): fn, ht, it, Jt

### Community 17 - "Editor Registration"
Cohesion: 0.05
Nodes (5): arc(), o(), ot(), quadraticCurveTo(), roundRect()

### Community 18 - "HTML Finalize Hooks"
Cohesion: 0.05
Nodes (16): an, ct, ee, je, Ne, Re(), Ce(), _e() (+8 more)

### Community 21 - "Minified Worker Vars"
Cohesion: 0.04
Nodes (16): _, cn, dimensions(), dn, Ft, hn, Kt, ln (+8 more)

### Community 23 - "Page Cleanup"
Cohesion: 0.06
Nodes (3): l(), M(), Q

### Community 25 - "Runtime Constructors"
Cohesion: 0.08
Nodes (8): f(), h(), c(), d(), f(), h(), v(), p()

### Community 26 - "Viewport Transform"
Cohesion: 0.07
Nodes (4): translate(), v(), xt, y()

### Community 30 - "Frontend Scan UI"
Cohesion: 0.13
Nodes (38): addStep(), askPageLimit(), cleanup(), onBackdrop(), onCancel(), onOption(), closeEventSource(), dataUrlToBytes() (+30 more)

### Community 31 - "Optional Content"
Cohesion: 0.14
Nodes (10): f(), d(), f(), y(), ce, G(), S(), te() (+2 more)

### Community 32 - "Decimal Formatting"
Cohesion: 0.06
Nodes (12): ge, he, be(), de(), _e(), Ie(), Ve(), xe() (+4 more)

### Community 33 - "Canvas Path Ops"
Cohesion: 0.06
Nodes (17): au(), du(), e0(), fu(), hu(), Jp(), k, Me() (+9 more)

### Community 34 - "Text Extraction"
Cohesion: 0.06
Nodes (4): O(), Y, A(), p()

### Community 38 - "HTML Clean"
Cohesion: 0.06
Nodes (5): dt, le(), ut, vt, xt

### Community 42 - "PDF Objects Fetch"
Cohesion: 0.08
Nodes (4): arcTo(), c(), PDFObjects, rect()

### Community 45 - "Auto Scan Core"
Cohesion: 0.09
Nodes (26): auto_black_point(), black_point_stretch(), cut_dark_edge_bands(), edge_darkness_profile(), enhance_reference_look(), find_document_contour(), high_pass_flatten(), measure_reference_aspect() (+18 more)

### Community 48 - "Flask Scan API"
Cohesion: 0.11
Nodes (22): Vercel entrypoint for the Flask shell and local-first scanner UI., api_image(), api_pdf(), api_scan(), api_scan_pdf(), api_scan_pdf_progress(), api_scan_pdf_start(), _cleanup_old_jobs() (+14 more)

### Community 50 - "Reference Template Alignment"
Cohesion: 0.10
Nodes (22): align_to_reference_template(), auto_trim_margins(), measure_reference_size(), Cut pure-white warp-fill bands at the edges (post-rectify/deskew). Drops…, Cut a warp-smeared band at the top edge, if present. Perspective extrapolation…, Return reference.png's (height, width), or None when unavailable., Align a known reference-photo page with SIFT/RANSAC when possible. This is a…, Erase spiral-binding rings overlapping the page (inpaint with paper). Rings are… (+14 more)

### Community 51 - "Map Operations"
Cohesion: 0.10
Nodes (4): be(), de(), on, se()

### Community 54 - "PDF Document Loading"
Cohesion: 0.11
Nodes (6): _fetchDocument(), getDataProp(), getDocument(), getUrlProp(), PDFDocumentLoadingTask, PDFWorker

### Community 55 - "Project Docs UI"
Cohesion: 0.12
Nodes (19): Automated Parameter Selection Goal, Crop Module (Planned), Java Scan Package, Main.java, Python Document Scan Code, RScan DocumentScanner Project, Document Scan API (Planned), Scan Class (+11 more)

### Community 56 - "Date Drawing"
Cohesion: 0.11
Nodes (5): ie(), le(), me(), se(), tt

### Community 61 - "JS Dependencies Manifest"
Cohesion: 0.12
Nodes (16): dependencies, pdf-lib, pdfjs-dist, description, devDependencies, @types/bun, name, private (+8 more)

### Community 66 - "Deskew Quality Gate"
Cohesion: 0.18
Nodes (15): deskew(), estimate_skew_angle(), Estimate dominant text-line tilt in degrees (OpenCV rotation sign). Positive…, Rotate image to make text lines horizontal., Flatten ruling lines that only became visible after enhancement. Geometry…, residual_deskew(), downscale_to_width(), ink_bbox() (+7 more)

### Community 68 - "Minified Runtime Utils"
Cohesion: 0.20
Nodes (16): Br(), Ce(), dc(), dn(), ep(), Jf(), Jt(), Ko() (+8 more)

### Community 70 - "PDF Scan Ingest"
Cohesion: 0.19
Nodes (14): collect_pages(), iter_images_as_bgr(), iter_pdf_pages_as_bgr(), main(), _pixmap_to_bgr(), Scan PDF photos to reference quality. Feature: convert every page-photo of an…, Return list of BGR pages from a PDF, image, or image directory., Write BGR pages to a PDF, one page per image, original pixel sizes. (+6 more)

### Community 75 - "Minified Functions"
Cohesion: 0.29
Nodes (13): ac(), af(), Di(), ff(), fr(), Gl(), hf(), ic() (+5 more)

### Community 76 - "Dewarp Ruling Lines"
Cohesion: 0.20
Nodes (12): _adaptive_ink_mask(), dewarp_by_rulings(), _fit_line(), _probe_gray(), Ink/lines mask robust to uneven lighting (adaptive, inverted)., Long near-horizontal ruling-line segments in probe coords. Filters out the…, Least-squares y = m*x + c over segment endpoints. Returns (m, c)., Curl-aware dewarp: flatten ruling lines band-by-band (y-remap). Notebook pages… (+4 more)

### Community 77 - "Photo Scan Filters"
Cohesion: 0.20
Nodes (6): _map_array(), Stateless version of map() for the functional API below., Scan a BGR image without globals (functional equivalent of this module). Modes:…, Reference-quality scan with geometry fix (see auto_scan.py). Falls back to…, scan_image(), scan_photo_auto()

### Community 81 - "Minified Helpers"
Cohesion: 0.18
Nodes (12): cf(), df(), ec(), Hl(), Lo(), Mo(), nc(), No() (+4 more)

### Community 84 - "Encrypt Parsing"
Cohesion: 0.18
Nodes (3): ke(), re(), ue()

### Community 86 - "Data Events"
Cohesion: 0.20
Nodes (6): Cp(), ds(), g0(), gn(), pn(), ts()

### Community 100 - "Physics Ensemble Notes"
Cohesion: 0.53
Nodes (6): Canonical Ensemble, Grand Canonical Ensemble, Handwritten Ensemble Comparison Table, Microcanonical Ensemble, Partition Function Z, Probability Distribution rho(E)

### Community 105 - "Minified Shortcuts"
Cohesion: 0.40
Nodes (6): gc(), mc(), rp(), tp(), vc(), Wr()

### Community 115 - "Vercel Deploy Config"
Cohesion: 0.50
Nodes (3): builds, routes, version

## Ambiguous Edges - Review These
- `Grand Canonical Ensemble` → `Partition Function Z`  [AMBIGUOUS]
  IMG-20260905-WA0005.jpg · relation: shares_data_with

## Knowledge Gaps
- **26 isolated node(s):** `name`, `private`, `version`, `description`, `dev` (+21 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 944 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **58 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Grand Canonical Ensemble` and `Partition Function Z`?**
  _Edge tagged AMBIGUOUS (relation: shares_data_with) - confidence is low._
- **Why does `o()` connect `Editor Registration` to `Canvas Render Commands`, `Text Rendering Ops`, `Decode Utilities`, `Canvas Font Setup`, `Annotation Edit UI`, `Annotation Storage`, `SVG Annotation Layer`, `Worker Messaging`, `Range Readers`, `Render Layers`, `Runtime Constructors`, `Viewport Transform`, `Canvas Path Ops`, `PDF Objects Fetch`, `Edit Mode UI`, `Loopback Port`, `Editor Delete`, `PDF Page Proxy`, `Glyph Tables`, `Cancel Cleanup`?**
  _High betweenness centrality (0.152) - this node is a cross-community bridge._
- **Why does `m()` connect `Decode Utilities` to `Page Dictionary Access`, `Usable Pages`, `Worker Node Factory`, `Password Parsing`, `Element Binding`, `Draw Dimensions`, `Render Layers`, `Image Ops Queue`, `Document Handler`, `Encrypt Parsing`, `Print Attributes`, `Page Cleanup`, `Runtime Constructors`, `XRef Decrypt`, `Optional Content`?**
  _High betweenness centrality (0.150) - this node is a cross-community bridge._
- **Why does `W()` connect `Decode Utilities` to `Decimal Formatting`, `Annotation Creation`, `Glyph Calendar`, `Form Field Names`, `Font Fallback`, `Draw Dimensions`, `Rotate Operations`, `Layout Calculations`, `Editor Registration`, `Print Attributes`, `XFA Objects`, `Font Decrypt`, `Cleanup Passes`, `Runtime Constructors`, `Form Attachments`, `XRef Decrypt`, `Optional Content`?**
  _High betweenness centrality (0.132) - this node is a cross-community bridge._
- **Are the 23 inferred relationships involving `X` (e.g. with `u()` and `D()`) actually correct?**
  _`X` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `t()` (e.g. with `y()` and `f()`) actually correct?**
  _`t()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `U` (e.g. with `u()` and `ce()`) actually correct?**
  _`U` has 17 INFERRED edges - model-reasoned connections that need verification._