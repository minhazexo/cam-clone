#!/usr/bin/env python3
"""Benchmark the server PDF scan: serial vs parallel page scanning.

The parallel path is bounded by the CPUs the process may actually use
(`rscan.services.pdf_scan_service.scan_pages_parallel` -> `_usable_cpus`), so
what this prints is what the API can really do on *this* machine:

* multi-core machine -> the parallel run uses several threads and finishes
  faster (the scan stage is ~85% of the per-page cost and OpenCV releases the
  GIL, so the gain approaches ``min(pdf_max_workers, cpus)`` there);
* single-core machine (CI containers, small sandboxes) -> both runs take the
  same time by construction: the pool is capped at one worker instead of
  over-subscribing a CPU it does not have.

Usage (from the repository root)::

    python3 scripts/bench_pdf_scan.py                 # synthetic 8-page PDF
    python3 scripts/bench_pdf_scan.py --pdf in.pdf --pages 4
    python3 scripts/bench_pdf_scan.py --repeat 3       # median of 3 runs

This is a development tool. It never touches the parity fixtures and does not
scan anything the API would not scan.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402

from rscan.config import get_settings  # noqa: E402
from rscan.services import pdf_scan_service as svc  # noqa: E402
from rscan.services.pdf_scan_service import scan_pdf_file, scan_pdf_streaming  # noqa: E402


def make_sample_pdf(pages: int, out_path: str) -> str:
    """Write a synthetic ruled-and-typed document (what a scan job sees)."""
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        for y in range(60, 800, 22):
            page.draw_line((50, y), (545, y), color=(0.7, 0.7, 0.85), width=0.5)
        for n in range(28):
            page.insert_text(
                (70, 90 + n * 24),
                f"page {i + 1} line {n}: the quick brown fox jumps over the lazy dog",
                fontsize=11, color=(0, 0, 0),
            )
        page.draw_rect(pymupdf.Rect(45, 50, 550, 815), color=(0, 0, 0), width=1)
    doc.save(out_path)
    doc.close()
    return out_path


def timed(func, *args) -> float:
    started = time.perf_counter()
    func(*args)
    return time.perf_counter() - started


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", default=None, help="PDF to scan (default: synthetic)")
    parser.add_argument("--pages", type=int, default=8, help="pages in the synthetic PDF")
    parser.add_argument("--repeat", type=int, default=1, help="take the median of N runs")
    args = parser.parse_args(argv)

    settings = get_settings()
    cpus = svc._usable_cpus()
    workers = max(1, min(settings.pdf_max_workers, cpus, max(1, args.pages)))

    tmp = Path(tempfile.mkdtemp(prefix="rscan_bench_"))
    source = args.pdf or make_sample_pdf(args.pages, str(tmp / "sample.pdf"))
    out_dir = tmp / "out"
    out_dir.mkdir(exist_ok=True)

    print(f"cpu budget (affinity) : {cpus}")
    print(f"pdf_max_workers setting: {settings.pdf_max_workers}")
    print(f"workers for this run   : {workers}")
    print(f"input                  : {source}")
    print()

    with pymupdf.open(source) as doc:
        pages_scanned = doc.page_count

    original_usable = svc._usable_cpus
    serial_runs, parallel_runs = [], []
    try:
        for i in range(args.repeat):
            svc._usable_cpus = lambda: 1  # force the historical single-thread behaviour
            serial_runs.append(timed(
                scan_pdf_file, source, str(out_dir / f"serial_{i}.pdf"), None, settings))
            svc._usable_cpus = original_usable
            parallel_runs.append(timed(
                scan_pdf_file, source, str(out_dir / f"parallel_{i}.pdf"), None, settings))
    finally:
        svc._usable_cpus = original_usable

    serial = statistics.median(serial_runs)
    parallel = statistics.median(parallel_runs)

    print(f"serial   (1 worker) : {serial:7.2f}s   {serial / pages_scanned:5.2f}s / page")
    print(f"parallel (pool of {workers}) : {parallel:7.2f}s   {parallel / pages_scanned:5.2f}s / page")
    if parallel > 0:
        speedup = serial / parallel
        print(f"speedup             : {speedup:7.2f}x")
        if workers == 1:
            print()
            print("note: this machine gives the process a single CPU, so the pool is")
            print("capped at 1 worker on purpose (no over-subscription). Run this on a")
            print("multi-core host to see the scaling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
