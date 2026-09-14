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

from flask import Flask, render_template, request, jsonify, send_file

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
    )
