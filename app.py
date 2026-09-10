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

from flask import Flask, render_template, request, jsonify, send_file

import cv2 as cv
import numpy as np

# Add the scan module to path so we can import it.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "RScan", "Python", "scan"))
from auto_scan import scan_photo_to_reference

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

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

    results = []
    for f in files:
        if not f or f.filename == "":
            continue
        if not _allowed(f.filename):
            continue
        data = f.read()
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
    f = request.files.get("file")
    if not f or f.filename == "":
        return jsonify(error="No file uploaded"), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_PDF_EXT:
        return jsonify(error="Only PDF files are accepted"), 400

    data = f.read()
    in_path = os.path.join(UPLOAD_DIR, f"in_{uuid.uuid4().hex[:8]}.pdf")
    with open(in_path, "wb") as fh:
        fh.write(data)

    try:
        from scan_pdf import scan_pdf_to_reference
        out_name = f"scanned_{uuid.uuid4().hex[:8]}.pdf"
        out_path = os.path.join(UPLOAD_DIR, out_name)
        scan_pdf_to_reference(in_path, out_path)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        try:
            os.remove(in_path)
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
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(path):
        return "not found", 404
    return send_file(path, mimetype="application/pdf",
                     as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
