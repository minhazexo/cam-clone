"""Unit tests for the storage layer (LocalTempStorage + sanitize_name)."""

import tempfile
import unittest
from pathlib import Path

from rscan.errors import ResultNotFoundError, StorageError
from rscan.storage import LocalTempStorage, sanitize_name


class SanitizeNameTest(unittest.TestCase):
    def test_keeps_safe_names(self):
        self.assertEqual(sanitize_name("scanned_ab12.pdf"), "scanned_ab12.pdf")
        self.assertEqual(sanitize_name("ab12cd34ef56.jpg"), "ab12cd34ef56.jpg")

    def test_strips_directories_and_leading_dots(self):
        self.assertEqual(sanitize_name("../../etc/passwd"), "_.._etc_passwd")
        self.assertEqual(sanitize_name(".hidden"), "hidden")

    def test_rejects_names_that_sanitize_to_nothing(self):
        for bad in ("", "..", "..."):
            with self.subTest(name=bad):
                with self.assertRaises(StorageError):
                    sanitize_name(bad)

    def test_separator_only_names_collapse_to_a_safe_token(self):
        self.assertEqual(sanitize_name("///"), "_")


class LocalTempStorageTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rscan_storage_"))
        self.storage = LocalTempStorage(self.root)

    def test_save_read_exists_delete_roundtrip(self):
        path = self.storage.save("a.txt", b"hello")
        self.assertEqual(path, self.root / "a.txt")
        self.assertTrue(self.storage.exists("a.txt"))
        self.assertEqual(self.storage.read("a.txt"), b"hello")
        self.assertEqual(self.storage.path("a.txt"), path)
        self.storage.delete("a.txt")
        self.assertFalse(self.storage.exists("a.txt"))

    def test_delete_is_idempotent(self):
        self.storage.delete("never-existed.bin")

    def test_path_raises_for_missing_artifact(self):
        with self.assertRaises(ResultNotFoundError):
            self.storage.path("missing.jpg")

    def test_exists_is_false_for_invalid_names(self):
        self.assertFalse(self.storage.exists(".."))
        self.assertFalse(self.storage.exists(""))

    def test_save_overwrites_atomically(self):
        self.storage.save("a.bin", b"one")
        self.storage.save("a.bin", b"two")
        self.assertEqual(self.storage.read("a.bin"), b"two")

    def test_no_partial_files_are_left_behind(self):
        self.storage.save("a.bin", b"one")
        leftovers = [p.name for p in self.root.iterdir() if p.name.endswith(".part")]
        self.assertEqual(leftovers, [])

    def test_write_path_points_inside_the_root_without_requiring_the_file(self):
        target = self.storage.write_path("out.pdf")
        self.assertEqual(target, self.root / "out.pdf")
        self.assertFalse(target.exists())

    def test_construction_creates_the_directory(self):
        nested = Path(tempfile.mkdtemp(prefix="rscan_storage_")) / "deep" / "dir"
        storage = LocalTempStorage(nested)
        self.assertTrue(storage.root.is_dir())


if __name__ == "__main__":
    unittest.main()
