# RScan Smart Scan Website Plan

## 1. Product Goal

Build a professional web application where users upload a PDF containing photographed or scanned document pages and receive a clean, readable Smart Scan PDF. The output should preserve the current scanner behavior:

- Automatic document alignment and perspective correction
- Background and page-shadow cleanup
- White paper appearance
- Strong, readable text strokes
- Preserved handwriting and colored ink where possible
- Correct page framing and consistent output dimensions
- Downloadable scanned PDF and optional page images

The product should feel like a focused document utility, not a generic upload form.

## 2. Current Baseline

The existing repository already contains:

- Flask web server in `app.py`
- Image scanning pipeline in `RScan/Python/scan/auto_scan.py`
- PDF rendering and PDF writing in `RScan/Python/scan/scan_pdf.py`
- Existing upload UI in `templates/index.html`
- Existing browser behavior in `static/js/app.js`
- Existing styles in `static/css/style.css`
- OpenCV, NumPy, PyMuPDF, and Flask dependencies

The current scanner is strongest for the known photographed-page workflow. The website plan must keep the scanner as a separate service boundary so its behavior can be tested independently from the UI.

## 3. Important Vercel Constraint

Vercel is a good fit for the frontend and lightweight API endpoints, but it is not a good place to run long, memory-heavy PDF jobs synchronously.

A production deployment should avoid this flow:

```text
Browser -> Vercel request -> render every PDF page -> scan every page -> return PDF
```

That flow can hit serverless timeout, memory, temporary-storage, request-size, and concurrent-processing limits.

## 3.1 Local-First Alternative

Yes, the product can be designed so the user's files never leave the user's device.

The browser can handle the complete workflow locally:

```text
User selects PDF
  -> browser reads PDF locally
  -> PDF.js renders each page
  -> WebAssembly/OpenCV processes each page
  -> pdf-lib or a PDF writer builds the result locally
  -> browser downloads the finished PDF
```

In this model:

- Vercel serves the frontend and scanner runtime assets
- No source PDF is uploaded to a server
- No background worker is required for the core scan flow
- The result is created in browser memory and downloaded locally
- The product can work offline after the first visit if built as a PWA

### What must change

The existing Python implementation cannot execute directly inside a normal browser. The scanner core must be ported or compiled:

1. Use PDF.js to render PDF pages in the browser.
2. Use OpenCV.js or a custom C++/Rust WebAssembly module for image operations.
3. Port the current geometry and enhancement stages from NumPy/OpenCV to the browser runtime.
4. Use pdf-lib or a WASM PDF writer to assemble scanned pages.
5. Run heavy work in Web Workers so the UI stays responsive.
6. Store no document data in analytics, logs, or server requests.

### Local-first tradeoffs

Advantages:

- Strong privacy story
- No server storage or signed-download infrastructure for the basic flow
- Lower hosting cost
- Works well with Vercel static hosting
- Can support offline/PWA usage

Tradeoffs:

- First load is larger because PDF, image, and WASM runtimes must download
- Old phones and low-memory devices may struggle with large PDFs
- Browser memory limits require page-by-page processing
- The current Python output will not match pixel-for-pixel until the algorithms are ported carefully
- Browser support and mobile performance need dedicated testing

### Recommended hybrid design

Make local processing the default and keep an optional server fallback:

```text
Small/normal PDF -> process locally in browser
Large PDF or weak device -> user chooses secure cloud processing
```

The UI should clearly show the selected mode:

- `On-device scan` means the file stays on the device.
- `Cloud scan` means the file is uploaded temporarily for processing.

Do not silently upload a file after promising local processing.

### Recommended migration path

Do not rewrite the scanner in one large step. Use this order:

1. Build the browser PDF preview with PDF.js.
2. Port grayscale, white-point, black-point, and sharpening operations.
3. Port perspective warp and document geometry.
4. Port background flattening and artifact cleanup.
5. Rebuild PDF output with pdf-lib.
6. Compare browser output against the existing Python reference fixture.
7. Add a Web Worker and memory-safe page queue.
8. Add optional cloud fallback only after local mode is stable.

The existing Python pipeline should remain as the golden-reference implementation during the port. Every browser change should be measured against the same source photo and `reference.png`.

Recommended production flow:

```text
Browser
  -> create upload session
  -> direct upload to object storage
  -> create scan job
  -> background worker processes PDF pages
  -> worker writes result to object storage
  -> browser polls or receives job completion
  -> secure download URL
```

## 4. Recommended Architecture

### 4.1 Frontend

Recommended options:

- Next.js on Vercel
- TypeScript
- Tailwind CSS or an existing component system
- Lucide icons
- Responsive layout with desktop and mobile states

The current Flask templates can be used for the MVP, but a Next.js frontend is the better long-term Vercel path because it gives stronger routing, loading states, deployment integration, and component structure.

### 4.2 API Layer

Use Vercel functions or a small API service for:

- Creating upload sessions
- Validating file metadata
- Creating scan jobs
- Returning job status
- Returning signed download URLs
- Deleting expired jobs

Do not make the API function perform the whole multi-page scan in the request lifecycle.

### 4.3 Scanner Worker

Keep the Python scanner in a worker process or container:

- Python 3.11+
- OpenCV
- NumPy
- PyMuPDF
- Existing `scan_photo_to_reference` pipeline
- Existing `scan_pdf_to_reference` pipeline

Possible worker hosting choices:

1. Modal or RunPod for image-heavy processing
2. Google Cloud Run Jobs
3. Railway, Render, or Fly.io worker service
4. A queue-backed VPS worker
5. Vercel function only for small, short image jobs during MVP

The worker should download the source object, process pages one at a time, upload page outputs, assemble the final PDF, upload the final PDF, and delete local temporary files.

### 4.4 Storage

Use object storage instead of local disk:

- Vercel Blob
- Cloudflare R2
- AWS S3
- Supabase Storage

Recommended object layout:

```text
uploads/{job_id}/source.pdf
jobs/{job_id}/pages/page-0001.jpg
jobs/{job_id}/pages/page-0002.jpg
jobs/{job_id}/result.pdf
```

Objects should be private. Downloads must use short-lived signed URLs.

### 4.5 Job State

Use a small database such as Supabase Postgres, Neon, or Redis-backed state.

Suggested job fields:

```text
id
status: created | uploading | queued | processing | completed | failed | expired
source_name
source_size_bytes
page_count
processed_pages
result_key
error_code
created_at
updated_at
expires_at
```

## 5. User Experience

### 5.1 Main Screen

The first screen should be the working scanner, not a marketing landing page.

Primary composition:

- Compact brand header
- Clear page title: `Make every page scan-ready`
- One prominent upload surface
- PDF-first call to action
- Secondary image upload option
- Supported formats and maximum size shown near the control
- A small recent-job area only when history is available

Avoid unnecessary explanatory cards and long marketing copy.

### 5.2 Upload Interaction

Support:

- Drag and drop
- File picker
- Paste where supported
- One PDF or a batch of images
- File type validation before upload
- File size validation before upload
- Visible upload progress
- Cancel upload
- Retry failed upload

The upload surface should show the selected file name, size, page estimate if available, and remove action before processing begins.

### 5.3 Processing Experience

Do not show a generic indefinite spinner.

Show:

- Current stage: `Uploading`, `Reading pages`, `Cleaning page 3 of 12`, `Building PDF`
- Progress bar
- Processed page count
- Estimated remaining work when possible
- A calm cancellation action
- Clear failure state with retry

For long jobs, the user should be able to leave the page and return using a job link if authentication or persistent job history is later added.

### 5.4 Results Experience

The result page should contain:

- Large preview of the first scanned page
- Page thumbnail rail or grid
- Before/after toggle for each page where the original is retained
- Page count and output dimensions
- Download scanned PDF as the primary action
- Download individual JPG pages as a secondary action
- Start another scan action
- Delete job action

Useful controls:

- Zoom
- Fit to screen
- Previous/next page
- Open preview
- Download page

### 5.5 Error States

Use human-readable errors:

- File type is not supported
- File is too large
- PDF contains no readable pages
- A page could not be rendered
- Scan worker timed out
- Output could not be generated
- Download link expired

Every error should offer a next action: retry, replace file, or start a new scan.

## 6. Visual Direction

The visual system should feel like a high-quality document tool:

- Warm white document canvas
- Ink-black primary text
- One confident accent color for actions
- Restrained borders and shadows
- Strong typography hierarchy
- Dense but comfortable workspace layout
- Maximum content width around 1200px
- Cards only for repeated files, previews, and dialogs
- Avoid excessive gradients, decorative blobs, and oversized hero sections

Suggested type direction:

- Use a distinctive sans-serif such as Manrope, Plus Jakarta Sans, or DM Sans
- Use a readable mono or tabular style only for metadata
- Keep body text compact and high contrast

Accessibility requirements:

- Keyboard accessible upload and controls
- Visible focus states
- Color contrast meeting WCAG AA
- Status updates announced with an ARIA live region
- Reduced-motion support
- Buttons with icons and accessible labels

## 7. API Contract

### Create upload session

```http
POST /api/uploads
Content-Type: application/json
```

Request:

```json
{
  "filename": "notes.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 1843200
}
```

Response:

```json
{
  "jobId": "job_123",
  "uploadUrl": "signed-upload-url",
  "expiresAt": "2026-09-12T12:00:00Z"
}
```

### Start scan

```http
POST /api/jobs/{jobId}/start
```

Response:

```json
{
  "jobId": "job_123",
  "status": "queued"
}
```

### Job status

```http
GET /api/jobs/{jobId}
```

Response:

```json
{
  "jobId": "job_123",
  "status": "processing",
  "pageCount": 12,
  "processedPages": 7,
  "stage": "Cleaning page 7 of 12",
  "result": null
}
```

Completed response:

```json
{
  "jobId": "job_123",
  "status": "completed",
  "pageCount": 12,
  "processedPages": 12,
  "result": {
    "pdfUrl": "signed-download-url",
    "pages": [
      {
        "page": 1,
        "width": 893,
        "height": 1263,
        "imageUrl": "signed-page-url"
      }
    ]
  }
}
```

## 8. PDF Processing Plan

### MVP

- Accept one PDF
- Render each page using PyMuPDF
- Send each rendered page through `scan_photo_to_reference`
- Write a scanned PDF
- Store result temporarily or in object storage
- Return a download link

### Production

- Detect page count before queueing
- Enforce page limit
- Process one page at a time to limit memory
- Upload page progress after every completed page
- Retry individual pages
- Continue or fail according to a documented policy
- Preserve page order
- Record processing duration per page
- Delete source and output objects after retention expiry

Recommended initial limits:

- Maximum file size: 25 MB
- Maximum pages: 50
- Maximum single-page rendered pixels: configured worker limit
- Maximum concurrent jobs per anonymous client: 1

These limits should be configurable through environment variables.

## 9. Security and Abuse Prevention

Required before public launch:

- Validate extension and MIME type
- Inspect file signature, not just filename
- Limit upload size and page count
- Reject encrypted or malformed PDFs with a clear message
- Use private storage and signed URLs
- Never expose local filesystem paths
- Sanitize original filenames
- Add rate limiting per IP or session
- Add request timeouts
- Use a job TTL and automatic cleanup
- Scan uploaded files with a malware scanner if the service will be public
- Do not log document contents or signed URLs
- Add CORS restrictions if frontend and API use separate domains

## 10. Vercel Deployment Strategy

### Recommended production split

```text
Vercel
  - Next.js frontend
  - upload-session API
  - job-status API
  - signed URL API

Worker service
  - Python/OpenCV/PyMuPDF
  - queue consumer
  - PDF rendering and scanning

Storage
  - R2/S3/Vercel Blob

Database/queue
  - Supabase/Neon + Redis or a managed queue
```

### Environment variables

```text
STORAGE_ENDPOINT
STORAGE_BUCKET
STORAGE_ACCESS_KEY
STORAGE_SECRET_KEY
DATABASE_URL
QUEUE_URL
WORKER_CALLBACK_SECRET
MAX_UPLOAD_MB
MAX_PAGES
JOB_TTL_MINUTES
```

Never commit these values.

### Preview environments

Use separate storage prefixes and databases for preview deployments:

```text
preview/{git_sha}/...
production/...
```

## 11. Implementation Phases

### Phase 1: Scanner service hardening

- Extract scanner code behind a clean Python service interface
- Add deterministic output options
- Remove fixture-specific assumptions from generic scanning
- Keep reference calibration available only for the intended workflow
- Add PDF page-by-page tests
- Add timeout and memory logging

### Phase 2: API and storage MVP

- Add upload session endpoint
- Add object storage adapter
- Add job table
- Add scan job creation endpoint
- Add status endpoint
- Add signed result URL endpoint
- Keep local Flask mode for development

### Phase 3: Professional frontend

- Migrate or refactor current templates into a component-based UI
- Build upload, progress, error, and results states
- Add responsive mobile layout
- Add page preview and page navigation
- Add download and retry flows
- Add accessibility states

### Phase 4: Background worker

- Move PDF processing out of the request lifecycle
- Add queue consumer
- Add progress callbacks
- Add page-level retry
- Add cleanup job
- Add structured logs and metrics

### Phase 5: Vercel production deployment

- Deploy frontend to Vercel
- Deploy API functions
- Deploy worker separately
- Configure private storage and signed URLs
- Add production environment variables
- Add rate limits and monitoring
- Run production smoke tests

## 12. Testing Strategy

### Scanner tests

- Known source photo produces expected dimensions
- Top, bottom, left, and right framing bounds
- Text sharpness regression metric
- Background whiteness metric
- Ink density metric
- Color preservation metric
- PDF pages preserve order
- Blank or malformed page handling

### API tests

- Upload session validation
- Unsupported file rejection
- Oversize file rejection
- Job creation
- Status transitions
- Failed job response
- Signed URL expiry
- Cleanup behavior

### Frontend tests

- Drag and drop upload
- Keyboard upload
- Progress state
- Retry state
- Empty result state
- PDF download
- Page preview navigation
- Mobile viewport layout
- Screen-reader labels

### Visual regression

Use Playwright screenshots for:

- Desktop upload state
- Mobile upload state
- Processing state
- Completed multi-page result
- Error state
- PDF preview state

## 13. Definition of Done

The website is ready for public beta when:

- A user can upload a PDF containing photographed pages
- The job continues safely outside the browser request lifecycle
- Every page is scanned using the verified RScan pipeline
- The result PDF preserves page order and readable text
- The user sees real progress and useful errors
- The result can be downloaded from a private signed URL
- Files expire automatically
- The UI works on mobile and desktop
- No secrets or local paths are exposed
- Scanner, API, worker, and frontend tests pass
- A Vercel preview and production deployment both work

## 14. Recommended First Build Order

1. Keep the current Flask app as the local scanner reference implementation.
2. Add a clean `scanner_service` wrapper around PDF and image processing.
3. Add job-oriented API models and a storage abstraction.
4. Build the professional upload/progress/results UI against mocked job responses.
5. Add the real worker and queue.
6. Deploy the frontend to Vercel and the worker separately.
7. Run visual and scanner regression tests using the existing reference fixture.

This order keeps the verified image-processing behavior stable while the product and deployment layers evolve around it.

## 15. Implemented In This Repository

The first local-first implementation slice is now present:

- PDF.js renders PDF pages in the browser.
- `static/js/scan-worker.js` performs local image enhancement in a Web Worker.
- pdf-lib assembles the processed pages into a downloadable PDF locally.
- The browser enforces local file-size and page-count limits.
- PDF page dimensions are preserved when building the result PDF.
- Worker failures produce a visible error instead of an endless spinner.
- `api/index.py` and `vercel.json` provide a Vercel entrypoint for the Flask shell.
- The legacy server image endpoint rejects PDFs and the PDF download route validates generated filenames.

The remaining production work is self-hosting pinned PDF.js/pdf-lib assets, porting the full Python geometry pipeline to WebAssembly/OpenCV.js for closer pixel parity, and adding a browser visual-regression suite.

## 16. Bun Commands

The frontend runtime is now managed with Bun:

```text
bun install       # install pinned browser dependencies
bun run build     # bundle PDF.js, pdf-lib, and the PDF worker locally
bun run check     # verify generated browser assets
bun run dev       # build assets and start the Flask development server
```

The generated files in `static/vendor/` are deployment assets and should be included in the repository. `node_modules/` remains local-only and is ignored.
