"""RScan Web — CamScanner-style document scanner website.

Run:
    pip install -r requirements.txt
    python app.py

Then open http://localhost:5000 in your browser.
"""

import os
import sys
import uuid
import tempfile
import time
import logging
import threading
import queue
import json

from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context

import cv2 as cv
import numpy as np

# Add the scan module to path so we can import it.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "RScan", "Python", "scan"))
from auto_scan import scan_photo_to_reference

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

LOG_LEVEL = logging.DEBUG if os.environ.get("RSCAN_DEBUG", "0") == "1" else logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("rscan.app")
logger.setLevel(LOG_LEVEL)

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "rscan_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
ALLOWED_PDF_EXT = {".pdf"}

# ── SSE Job Store ─────────────────────────────────────────────────────────
# Maps job_id -> {"queue": Queue, "pdf_name": str | None, "error": str | None}
_job_store: dict = {}
_job_store_lock = threading.Lock()

JOB_TTL_SECONDS = 600  # clean up old jobs after 10 minutes


def _new_job() -> str:
    job_id = uuid.uuid4().hex
    with _job_store_lock:
        _job_store[job_id] = {
            "queue": queue.Queue(),
            "pdf_name": None,
            "error": None,
            "created_at": time.time(),
        }
    return job_id


def _push(job_id: str, event_dict: dict):
    """Push a JSON-serialisable dict as an SSE event into the job queue."""
    with _job_store_lock:
        job = _job_store.get(job_id)
    if job:
        job["queue"].put(json.dumps(event_dict))


def _cleanup_old_jobs():
    now = time.time()
    with _job_store_lock:
        stale = [jid for jid, j in _job_store.items()
                 if now - j.get("created_at", 0) > JOB_TTL_SECONDS]
        for jid in stale:
            del _job_store[jid]


def _allowed(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_IMAGE_EXT | ALLOWED_PDF_EXT


# ── Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Accept one or more image files, scan each, return scanned images."""
    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify(error="No files uploaded"), 400

    seen = set()
    unique_files = []
    for f in files:
        if not f or f.filename == "":
            continue
        data = f.read()
        signature = (f.filename, len(data), f.content_type or "")
        if signature in seen:
            continue
        seen.add(signature)
        unique_files.append((f, data))

    results = []
    for f, data in unique_files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext in ALLOWED_PDF_EXT:
            return jsonify(error="PDF files are processed locally in the browser. Use the PDF scan control."), 400
        if ext not in ALLOWED_IMAGE_EXT:
            continue

        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv.imdecode(arr, cv.IMREAD_COLOR)
        if img is None:
            continue

        try:
            scanned = scan_photo_to_reference(img)
        except Exception as e:
            results.append({"name": f.filename, "error": str(e)})
            continue

        ok, buf = cv.imencode(".jpg", scanned, [int(cv.IMWRITE_JPEG_QUALITY), 95])
        if not ok:
            results.append({"name": f.filename, "error": "JPEG encode failed"})
            continue

        file_id = uuid.uuid4().hex[:12]
        out_path = os.path.join(UPLOAD_DIR, f"{file_id}.jpg")
        with open(out_path, "wb") as fh:
            fh.write(buf.tobytes())

        results.append({
            "name": f.filename,
            "id": file_id,
            "width": scanned.shape[1],
            "height": scanned.shape[0],
        })

    return jsonify(pages=results)


# ── Legacy single-shot PDF scan (kept as fallback) ───────────────────────

@app.route("/api/scan-pdf", methods=["POST"])
def api_scan_pdf():
    """Accept a PDF, scan every page, return scanned PDF."""
    started = time.time()
    f = request.files.get("file")
    if not f or f.filename == "":
        logger.warning("scan-pdf: no file uploaded")
        return jsonify(error="No file uploaded"), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_PDF_EXT:
        logger.warning("scan-pdf: rejected non-pdf file=%s", f.filename)
        return jsonify(error="Only PDF files are accepted"), 400

    page_limit = request.form.get("page_limit", type=int)
    if page_limit is not None and page_limit < 1:
        logger.warning("scan-pdf: invalid page_limit=%s for file=%s", page_limit, f.filename)
        return jsonify(error="page_limit must be at least 1"), 400

    data = f.read()
    in_path = os.path.join(UPLOAD_DIR, f"in_{uuid.uuid4().hex[:8]}.pdf")
    logger.info("scan-pdf: received file=%s bytes=%d page_limit=%s", f.filename, len(data), page_limit)
    with open(in_path, "wb") as fh:
        fh.write(data)

    try:
        from scan_pdf import scan_pdf_to_reference
        out_name = f"scanned_{uuid.uuid4().hex[:8]}.pdf"
        out_path = os.path.join(UPLOAD_DIR, out_name)
        logger.info("scan-pdf: start scan input=%s output=%s", in_path, out_path)
        scan_pdf_to_reference(in_path, out_path, page_limit=page_limit)
        logger.info("scan-pdf: success file=%s elapsed=%.2fs", f.filename, time.time() - started)
    except Exception as e:
        logger.exception("scan-pdf: failed file=%s elapsed=%.2fs error=%s", f.filename, time.time() - started, str(e))
        return jsonify(error=str(e)), 500
    finally:
        try:
            os.remove(in_path)
            logger.info("scan-pdf: removed temp input=%s", in_path)
        except OSError:
            pass

    return jsonify(pdf=out_name)


# ── SSE-based streaming PDF scan ─────────────────────────────────────────

@app.route("/api/scan-pdf-start", methods=["POST"])
def api_scan_pdf_start():
    """Receive PDF, queue a background scan job, return job_id immediately."""
    _cleanup_old_jobs()

    f = request.files.get("file")
    if not f or f.filename == "":
        return jsonify(error="No file uploaded"), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_PDF_EXT:
        return jsonify(error="Only PDF files are accepted"), 400

    page_limit = request.form.get("page_limit", type=int)
    if page_limit is not None and page_limit < 1:
        return jsonify(error="page_limit must be at least 1"), 400

    data = f.read()
    original_name = f.filename
    in_path = os.path.join(UPLOAD_DIR, f"in_{uuid.uuid4().hex[:8]}.pdf")
    with open(in_path, "wb") as fh:
        fh.write(data)

    job_id = _new_job()
    logger.info("scan-pdf-start: job_id=%s file=%s bytes=%d", job_id, original_name, len(data))

    # Launch background worker thread
    thread = threading.Thread(
        target=_scan_pdf_worker,
        args=(job_id, in_path, original_name, page_limit),
        daemon=True,
    )
    thread.start()

    return jsonify(job_id=job_id)


def _scan_pdf_worker(job_id: str, in_path: str, original_name: str, page_limit):
    """Background thread: scan PDF page-by-page and push SSE events."""
    started = time.time()
    logger.info("scan-pdf-worker: start job_id=%s file=%s", job_id, original_name)

    try:
        # -- Import here so path is already set up
        import pymupdf  # noqa: F401 — just to trigger ImportError early if missing
        from scan_pdf import collect_pages, save_bgr_pages_as_pdf

        # Step 1: load all pages (renders PDF pages to BGR images at 200 DPI;
        # 300 DPI preserves nothing extra here — the embedded photos are ~288
        # DPI — while nearly doubling pixels and JPEG bytes per page)
        _push(job_id, {"type": "loading"})
        pages = collect_pages(in_path, dpi=200)
        total = len(pages)
        if page_limit is not None:
            pages = pages[:page_limit]
            total_to_scan = len(pages)
        else:
            total_to_scan = total

        _push(job_id, {"type": "detected", "total": total_to_scan})
        logger.info("scan-pdf-worker: job_id=%s detected pages=%d", job_id, total_to_scan)

        # Step 2: scan pages in parallel across CPU cores
        from concurrent.futures import ThreadPoolExecutor, as_completed
        _push(job_id, {"type": "scanning", "page": 1, "total": total_to_scan})

        completed_count = 0
        scanned_map = {}
        num_workers = min(max(1, os.cpu_count() or 4), 8)

        def _process_page_item(item):
            idx, page_img = item
            # output_scale=1.0: the old 2.0 Lanczos upscale blurs text edges
            # while quadrupling pixels (measured sharpness 457 -> 66).
            return idx, scan_photo_to_reference(page_img, output_scale=1.0)

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(_process_page_item, (i, page)) for i, page in enumerate(pages)]
            for future in as_completed(futures):
                idx, out = future.result()
                scanned_map[idx] = out
                completed_count += 1
                _push(job_id, {"type": "page_done", "page": completed_count, "total": total_to_scan})

        scanned = [scanned_map[i] for i in range(len(pages))]

        # Step 3: assemble PDF on uniform A4 pages, image filling the page
        # (margin=0 full-bleed, aspect preserved) instead of 1-pixel-per-point
        # variable-size pages.
        _push(job_id, {"type": "assembling"})
        out_name = f"scanned_{uuid.uuid4().hex[:8]}.pdf"
        out_path = os.path.join(UPLOAD_DIR, out_name)
        save_bgr_pages_as_pdf(scanned, out_path, jpeg_quality=78,
                              page_size="A4", margin=0.0)

        elapsed = time.time() - started
        logger.info("scan-pdf-worker: job_id=%s done elapsed=%.2fs output=%s", job_id, elapsed, out_name)
        _push(job_id, {"type": "done", "pdf": out_name, "elapsed": round(elapsed, 1)})

    except Exception as e:
        logger.exception("scan-pdf-worker: job_id=%s error=%s", job_id, str(e))
        _push(job_id, {"type": "error", "message": str(e)})
    finally:
        try:
            os.remove(in_path)
        except OSError:
            pass
        # Signal the SSE generator to close
        _push(job_id, {"type": "_eof"})


@app.route("/api/scan-pdf-progress/<job_id>")
def api_scan_pdf_progress(job_id):
    """SSE endpoint: streams scan progress events for a given job."""
    with _job_store_lock:
        job = _job_store.get(job_id)
    if not job:
        return jsonify(error="Job not found"), 404

    def generate():
        q = job["queue"]
        while True:
            try:
                payload = q.get(timeout=30)
            except queue.Empty:
                # Send a keepalive comment so the connection doesn't time out
                yield ": keepalive\n\n"
                continue

            yield f"data: {payload}\n\n"

            parsed = json.loads(payload)
            if parsed.get("type") in ("done", "error", "_eof"):
                break

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # disable nginx buffering if present
    }
    return Response(stream_with_context(generate()), headers=headers)


@app.route("/api/image/<file_id>")
def api_image(file_id):
    """Serve a scanned image by its ID."""
    path = os.path.join(UPLOAD_DIR, f"{file_id}.jpg")
    if not os.path.isfile(path):
        return "not found", 404
    return send_file(path, mimetype="image/jpeg")


@app.route("/api/pdf/<filename>")
def api_pdf(filename):
    """Serve a scanned PDF by filename."""
    safe_name = os.path.basename(filename)
    if safe_name != filename or not safe_name.startswith("scanned_"):
        return "not found", 404
    path = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.isfile(path):
        return "not found", 404
    return send_file(path, mimetype="application/pdf",
                     as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("RSCAN_DEBUG", "0") == "1",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        threaded=True,   # Required for SSE + background threads
    )
