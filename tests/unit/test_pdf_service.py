"""Unit tests for the shared parallel page scanner used by both PDF endpoints.

The guarantees covered here are the ones the API depends on:

* results come back in document order (page 0 first) no matter which thread
  finishes first;
* ``page_done`` progress is monotonic and ends at the total, so the SSE
  progress bar can never jump backwards;
* PDF pages are scanned at ``output_scale=1.0`` — the scanner's own default
  is 2.0, which would silently quadruple pixels and blur text;
* the worker pool never exceeds the CPUs we may actually use;
* a scan failure propagates instead of leaving a half-filled result.
"""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from rscan.config import get_settings
from rscan.services import pdf_scan_service as svc
from rscan.services.pdf_scan_service import scan_pages_parallel


def _page(value: int = 0) -> np.ndarray:
    return np.full((3, 3, 3), value, dtype=np.uint8)


class ScanPagesParallelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = get_settings()

    def test_returns_pages_in_document_order(self) -> None:
        pages = [_page(i) for i in range(6)]
        out = scan_pages_parallel(pages, self.settings, scan_fn=lambda p: p * 2)
        self.assertEqual(len(out), 6)
        for index, page in enumerate(out):
            self.assertEqual(int(page[0, 0, 0]), index * 2,
                             f"page {index} came back out of order")

    def test_progress_is_monotonic_and_completes(self) -> None:
        pages = [_page(i) for i in range(5)]
        seen: list[tuple[int, int]] = []
        scan_pages_parallel(
            pages, self.settings,
            on_page_done=lambda done, total: seen.append((done, total)),
        )
        self.assertEqual([done for done, _ in seen], [1, 2, 3, 4, 5])
        self.assertTrue(all(total == 5 for _, total in seen))

    def test_empty_input_is_a_no_op(self) -> None:
        self.assertEqual(scan_pages_parallel([], self.settings), [])

    def test_pdf_pages_are_scanned_at_scale_one(self) -> None:
        # Regression guard: scan_photo_to_reference's default output_scale is
        # 2.0 (correct for phone photos, wrong for 200-DPI rendered pages).
        with mock.patch.object(svc, "scan_photo_to_reference") as scanner:
            scanner.return_value = "scanned"
            svc._scan_pdf_page(_page())
        scanner.assert_called_once()
        self.assertEqual(scanner.call_args.kwargs.get("output_scale"), 1.0)

    def test_pool_is_bounded_by_cpus_and_page_count(self) -> None:
        self.assertGreaterEqual(svc._usable_cpus(), 1)
        pages = [_page(i) for i in range(10)]
        captured: dict[str, int] = {}
        real_executor = svc.ThreadPoolExecutor

        def spy(max_workers: int | None = None, **kwargs):
            captured["max_workers"] = int(max_workers or 0)
            return real_executor(max_workers=max_workers, **kwargs)

        with mock.patch.object(svc, "ThreadPoolExecutor", side_effect=spy):
            scan_pages_parallel(pages, self.settings)

        workers = captured["max_workers"]
        self.assertGreaterEqual(workers, 1)
        self.assertLessEqual(workers, self.settings.pdf_max_workers)
        self.assertLessEqual(workers, svc._usable_cpus())   # never over-subscribe
        self.assertLessEqual(workers, len(pages))           # no idle threads

    def test_a_scan_failure_propagates(self) -> None:
        def boom(_page_img: np.ndarray) -> np.ndarray:
            raise RuntimeError("scanner exploded")

        with self.assertRaises(RuntimeError):
            scan_pages_parallel([_page()], self.settings, scan_fn=boom)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
