"""Unit tests for configuration and the error hierarchy."""

import os
import unittest
from pathlib import Path
from unittest import mock

from rscan.config import PROJECT_ROOT, Settings, get_settings, reset_settings_cache
from rscan.errors import (
    InvalidPageLimitError,
    InvalidUploadError,
    JobNotFoundError,
    PdfProcessingError,
    RScanError,
    ResultNotFoundError,
    ScanProcessingError,
    StorageError,
    UnsupportedFileTypeError,
)


class SettingsTest(unittest.TestCase):
    def setUp(self):
        reset_settings_cache()

    def tearDown(self):
        reset_settings_cache()

    def test_project_root_contains_the_expected_directories(self):
        self.assertTrue((PROJECT_ROOT / "rscan").is_dir())
        self.assertTrue((PROJECT_ROOT / "templates").is_dir())
        self.assertTrue((PROJECT_ROOT / "static").is_dir())

    def test_paths_are_absolute_and_outside_the_cwd(self):
        settings = Settings()
        self.assertTrue(settings.template_folder.is_absolute())
        self.assertTrue(settings.static_folder.is_absolute())
        self.assertIsInstance(settings.upload_dir, Path)

    def test_defaults_match_the_documented_product_limits(self):
        settings = Settings()
        self.assertEqual(settings.max_upload_bytes, 50 * 1024 * 1024)
        self.assertEqual(settings.image_jpeg_quality, 95)
        self.assertEqual(settings.pdf_dpi, 200)
        self.assertEqual(settings.pdf_jpeg_quality, 78)
        self.assertEqual(settings.pdf_page_size, "A4")
        self.assertEqual(settings.job_ttl_seconds, 600)
        self.assertEqual(settings.sse_keepalive_seconds, 30)

    def test_extension_helpers(self):
        settings = Settings()
        self.assertTrue(settings.is_allowed_image("PHOTO.JPG"))
        self.assertTrue(settings.is_allowed_image("scan.tiff"))
        self.assertFalse(settings.is_allowed_image("doc.pdf"))
        self.assertTrue(settings.is_allowed_pdf("Doc.PDF"))
        self.assertFalse(settings.is_allowed_pdf("photo.jpg"))

    def test_debug_and_port_come_from_environment(self):
        with mock.patch.dict(os.environ, {"RSCAN_DEBUG": "1", "PORT": "8123"}):
            settings = Settings()
        self.assertTrue(settings.debug)
        self.assertEqual(settings.port, 8123)

    def test_junk_integer_env_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"PORT": "not-a-port"}):
            settings = Settings()
        self.assertEqual(settings.port, 5000)

    def test_get_settings_is_cached_until_reset(self):
        first = get_settings()
        self.assertIs(first, get_settings())
        reset_settings_cache()
        self.assertIsNot(first, get_settings())

    def test_settings_are_immutable(self):
        settings = Settings()
        with self.assertRaises(Exception):
            settings.pdf_dpi = 300  # type: ignore[misc]


class ErrorHierarchyTest(unittest.TestCase):
    def test_every_error_is_a_rscan_error_with_a_status(self):
        cases = {
            InvalidUploadError: 400,
            UnsupportedFileTypeError: 400,
            InvalidPageLimitError: 400,
            ScanProcessingError: 500,
            PdfProcessingError: 500,
            JobNotFoundError: 404,
            StorageError: 500,
            ResultNotFoundError: 404,
        }
        for error_class, expected_status in cases.items():
            with self.subTest(error=error_class.__name__):
                error = error_class()
                self.assertIsInstance(error, RScanError)
                self.assertEqual(error.http_status, expected_status)
                self.assertTrue(error.public_message)

    def test_custom_message_overrides_the_default(self):
        error = UnsupportedFileTypeError("Only PDF files are accepted")
        self.assertEqual(str(error), "Only PDF files are accepted")
        self.assertEqual(error.public_message, "Only PDF files are accepted")


if __name__ == "__main__":
    unittest.main()
