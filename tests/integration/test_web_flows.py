"""Integration tests: real Flask app, real services, isolated temp storage.

Every test drives the app through the Flask test client, exactly like the
browser does, so the request/response contract in ``docs/API.md`` is what gets
verified. Storage is redirected to a per-test temp directory, and PDF tests use
a low render DPI so the whole file stays fast.
"""

import io
import json
import tempfile
import time
import unittest
from pathlib import Path

import cv2 as cv
import numpy as np
import pymupdf

from rscan.config import Settings
from rscan.web import create_app

SSL_HEADERS = {"Content-Type": "multipart/form-data"}


def make_document_image(width=300, height=420):
    """Synthetic phone photo of a note page (grey paper, dark text bars)."""
    image = np.full((height, width, 3), 232, np.uint8)
    image[30:height - 30, 30:width - 30] = 246
    for y in range(50, height - 50, 36):
        image[y:y + 8, 45:width - 45] = 30
    image[:, :12] = (image[:, :12] * 0.6).astype(np.uint8)
    ok, buffer = cv.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


def make_pdf(page_count=2, jpeg_bytes=None):
    """A small PDF whose pages each embed one document photo."""
    jpeg_bytes = jpeg_bytes or make_document_image()
    doc = pymupdf.open()
    for _ in range(page_count):
        page = doc.new_page(width=300, height=420)
        page.insert_image(pymupdf.Rect(0, 0, 300, 420), stream=jpeg_bytes)
    data = doc.tobytes()
    doc.close()
    return data


class RScanAppTestCase(unittest.TestCase):
    """Base case: app wired to a temporary storage root."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rscan_it_"))
        self.settings = Settings(upload_dir=self.tmp, pdf_dpi=72)
        self.app = create_app(self.settings)
        self.client = self.app.test_client()

    def storage_files(self):
        return sorted(p.name for p in self.tmp.iterdir())

    def wait_for_removal(self, prefix, timeout=5.0):
        """Wait for background-worker cleanup (the job thread runs detached)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not [name for name in self.storage_files() if name.startswith(prefix)]:
                return True
            time.sleep(0.05)
        return False

    def post_scan(self, files):
        data = {}
        for index, (name, payload) in enumerate(files):
            data[f"files{index}"] = (io.BytesIO(payload), name)
        # Werkzeug expects the repeated "files" field for list uploads.
        data = {"files": [(io.BytesIO(payload), name) for name, payload in files]}
        return self.client.post("/api/scan", data=data, content_type="multipart/form-data")

    def post_pdf(self, path, payload, filename="input.pdf", **form):
        data = {"file": (io.BytesIO(payload), filename)}
        data.update(form)
        return self.client.post(path, data=data, content_type="multipart/form-data")


class HealthAndPagesTest(RScanAppTestCase):
    def test_health_probe(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok", "service": "rscan"})

    def test_home_page_renders_the_scan_shell(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        for marker in ("uploadZone", "fileInput", "btnImages", "btnPdf",
                       "processingSection", "stepLog", "resultsSection",
                       "resultsGrid", "pageLimitBackdrop", "js/app.js"):
            self.assertIn(marker, html)

    def test_on_device_page_renders_the_engine_shell(self):
        response = self.client.get("/scan-pdf")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        for marker in ("engineStatus", "btnPdf", "uploadZone",
                       "js/scanpdf.js", "vendor/runtime.js"):
            self.assertIn(marker, html)

    def test_unknown_api_route_answers_json(self):
        response = self.client.get("/api/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.get_json())

    def test_unknown_page_route_keeps_flask_html(self):
        response = self.client.get("/nope")
        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response.headers["Content-Type"])


class ImageScanFlowTest(RScanAppTestCase):
    def test_scan_requires_files(self):
        response = self.client.post("/api/scan", data={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "No files uploaded")

    def test_scan_returns_page_descriptors_and_serves_the_image(self):
        response = self.post_scan([("photo.jpg", make_document_image())])
        self.assertEqual(response.status_code, 200)
        pages = response.get_json()["pages"]
        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertEqual(page["name"], "photo.jpg")
        self.assertGreater(page["width"], 0)
        self.assertGreater(page["height"], 0)

        image = self.client.get(f"/api/image/{page['id']}")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["Content-Type"], "image/jpeg")
        self.assertGreater(len(image.data), 100)

    def test_scan_dedupes_identical_uploads(self):
        payload = make_document_image()
        response = self.post_scan([("a.jpg", payload), ("a.jpg", payload)])
        self.assertEqual(len(response.get_json()["pages"]), 1)

    def test_scan_skips_unsupported_extensions(self):
        response = self.post_scan([("notes.txt", b"hello")])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["pages"], [])

    def test_scan_skips_undecodable_images(self):
        response = self.post_scan([("broken.jpg", b"not really a jpeg")])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["pages"], [])

    def test_scan_rejects_pdfs_with_a_pointer_to_the_pdf_flow(self):
        response = self.post_scan([("doc.pdf", make_pdf(1))])
        self.assertEqual(response.status_code, 400)
        self.assertIn("PDF", response.get_json()["error"])

    def test_missing_image_artifact_is_a_plain_404(self):
        response = self.client.get("/api/image/deadbeef")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_data(as_text=True), "not found")


class SyncPdfFlowTest(RScanAppTestCase):
    def test_scan_pdf_returns_a_downloadable_filename(self):
        response = self.post_pdf("/api/scan-pdf", make_pdf(2), page_limit="1")
        self.assertEqual(response.status_code, 200)
        name = response.get_json()["pdf"]
        self.assertTrue(name.startswith("scanned_"))
        self.assertTrue(name.endswith(".pdf"))

        download = self.client.get(f"/api/pdf/{name}")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.headers["Content-Type"], "application/pdf")
        self.assertIn("attachment", download.headers["Content-Disposition"])

    def test_scan_pdf_removes_the_temporary_input(self):
        self.post_pdf("/api/scan-pdf", make_pdf(1))
        self.assertEqual([name for name in self.storage_files() if name.startswith("in_")], [])

    def test_scan_pdf_validates_the_upload(self):
        missing = self.client.post("/api/scan-pdf", data={})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.get_json()["error"], "No file uploaded")

        wrong_type = self.post_pdf("/api/scan-pdf", b"hello", filename="notes.txt")
        self.assertEqual(wrong_type.status_code, 400)
        self.assertEqual(wrong_type.get_json()["error"], "Only PDF files are accepted")

    def test_scan_pdf_that_is_not_really_a_pdf_reports_a_processing_error(self):
        # Extension validation cannot see file contents, so a mislabelled file
        # reaches the PDF pipeline and fails there (500 + sanitised message).
        response = self.post_pdf("/api/scan-pdf", b"definitely not a pdf")
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.get_json())
        self.assertNotIn("Traceback", response.get_data(as_text=True))

    def test_scan_pdf_rejects_a_bad_page_limit(self):
        response = self.post_pdf("/api/scan-pdf", make_pdf(1), page_limit="0")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "page_limit must be at least 1")

    def test_pdf_download_rejects_unexpected_names(self):
        for name in ("evil.pdf", "notscanned_x.pdf"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(f"/api/pdf/{name}").status_code, 404)


class StreamingPdfJobTest(RScanAppTestCase):
    def _run_job(self, payload, **form):
        start = self.post_pdf("/api/scan-pdf-start", payload, **form)
        self.assertEqual(start.status_code, 200)
        job_id = start.get_json()["job_id"]
        self.assertTrue(job_id)

        stream = self.client.get(f"/api/scan-pdf-progress/{job_id}")
        self.assertEqual(stream.status_code, 200)
        self.assertEqual(stream.headers["Content-Type"], "text/event-stream")
        events = [json.loads(line[len("data: "):])
                  for line in stream.get_data(as_text=True).splitlines()
                  if line.startswith("data: ")]
        return job_id, events

    def test_job_streams_the_documented_event_order(self):
        job_id, events = self._run_job(make_pdf(2))
        types = [event["type"] for event in events]
        self.assertEqual(types[0], "loading")
        self.assertEqual(types[1], "detected")
        self.assertEqual(types[2], "scanning")
        self.assertIn("assembling", types)
        self.assertEqual(types[-1], "done")
        self.assertEqual(types.count("page_done"), 2)

        detected = events[1]
        self.assertEqual(detected["total"], 2)
        done = events[-1]
        self.assertTrue(done["pdf"].startswith("scanned_"))
        self.assertIn("elapsed", done)

        download = self.client.get(f"/api/pdf/{done['pdf']}")
        self.assertEqual(download.status_code, 200)

    def test_page_limit_limits_emitted_pages(self):
        _, events = self._run_job(make_pdf(2), page_limit="1")
        page_done = [event for event in events if event["type"] == "page_done"]
        self.assertEqual(len(page_done), 1)
        self.assertEqual(events[1]["total"], 1)

    def test_job_cleans_up_its_temporary_input(self):
        self._run_job(make_pdf(1))
        self.assertTrue(self.wait_for_removal("in_"),
                        f"temporary inputs left behind: {self.storage_files()}")

    def test_unknown_job_id_is_404(self):
        response = self.client.get("/api/scan-pdf-progress/nope")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "Job not found")

    def test_start_validates_the_upload(self):
        response = self.client.post("/api/scan-pdf-start", data={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "No file uploaded")


class ErrorHandlingTest(RScanAppTestCase):
    def test_oversized_requests_are_rejected_with_json(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 128
        response = self.post_scan([("big.jpg", b"x" * 4096)])
        self.assertEqual(response.status_code, 413)
        self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
