# Graph Knowledge Map — what `graphify-out/` says about this repo

Generated from `graph.json` (3144 nodes, 7911 edges, 125 communities) + `GRAPH_REPORT.md`. Build: AST 3119 nodes / semantic 26 nodes.

## 1. Where the nodes really are
~90% are minified `static/vendor/pdf.worker.js` + `runtime.js` (Bun output). Project code is a minority — this is why god nodes mislead:
- Reported gods `X(167), S()(147), t()(147), U(136), C(134)…` = vendor minified symbols. **Ignore for architecture.**
- Real hubs: `Flask Scan API` (25: app.py+index.py), `Auto Scan Core` (27), `Reference Template Alignment` (22), `Deskew Quality Gate` (16), `PDF Scan Ingest` (15), `Photo Scan Filters` (6), `Dewarp Ruling Lines` (12), `Frontend Scan UI` (40), `Project Docs UI` (19).

## 2. Verified cross-module edges (Surprising Connections, code-confirmed)
- `api_scan() --calls--> scan_photo_to_reference()` (app.py → auto_scan.py)
- `_scan_pdf_worker() --calls--> collect_pages()` + `save_bgr_pages_as_pdf()` (app.py → scan_pdf.py)
- `api_scan_pdf() --calls--> scan_pdf_to_reference()` (app.py → scan_pdf.py)
- `Flask --conceptually_related_to--> RScan Index Page` (requirements → templates)
All tagged INFERRED in graph but verified in source — promote to EXTRACTED mentally.

## 3. Hyperedges (group truths)
- Scan workflow: upload → processing → results sections (templates/index.html, EXTRACTED 1.0).
- Backend stack: flask + opencv + numpy + pymupdf (requirements.txt, EXTRACTED 1.0).
- Ensemble trio: micro/canonical/grand-canonical (JPG image, INFERRED 0.85) — true for the image, irrelevant to scanner.

## 4. Health & gaps (honest)
- 41 dangling edges, 2 self-loops, ~1878 collapsed `contains` edges — artifact of minified vendor AST, not project bugs.
- 1 AMBIGUOUS edge: `Grand Canonical Ensemble → Partition Function Z` (image guess, 0.2).
- 26 isolated + 58 thin communities: config leaves (`name, private, version`), one-off helpers (`NumPy`, `runtime.ts`, `scan-worker.js` solo). Expected.
- Cohesion: project pipelines 0.09-0.20 (Auto Scan 0.09, Flask API 0.11, Deskew Gate 0.18, Dewarp 0.20, Photo Filters 0.20); vendor clusters 0.04-0.08; physics image 0.53 (tight but off-topic); Vercel config 0.50.

## 5. How to query next
```
python -m graphify query "How does scan-pdf-start flow to SSE done?"
python -m graphify query "What calls scan_photo_to_reference?"
python -m graphify path "api_scan" "scan_photo_to_reference"
python -m graphify explain "auto_scan"
```
Open `graphify-out/graph.html` in browser; filter out `source_file contains vendor` to see project-only structure. Benchmark: 13.0x token reduction per query.
