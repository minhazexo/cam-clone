"""Background worker for server PDF scans.

One job == one daemon thread that:

    1. scans the uploaded PDF with ``services.pdf_scan_service`` (which emits
       loading/detected/scanning/page_done/assembling through a callback that
       pushes into the job's queue);
    2. stores the assembled PDF in the storage layer;
    3. emits the terminal ``done`` (or ``error``) event and always emits
       ``_eof`` so the SSE generator closes even when the scan failed;
    4. deletes the temporary input PDF.

Why a thread and not a task queue: the job's result is streamed back to the
same process over SSE, and the whole design is single-process by intent (see
``docs/DEPLOYMENT.md`` for the serverless caveats). ``daemon=True`` means a
process exit never hangs on a half-finished scan — the client sees the SSE
stream end and can retry.

Every log line here carries ``job_id`` on purpose: background failures are
otherwise impossible to correlate with a user report.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from rscan.config import Settings
from rscan.jobs import events
from rscan.jobs.job_store import JobStore
from rscan.services import pdf_scan_service
from rscan.storage import Storage

logger = logging.getLogger(__name__)


def run_pdf_scan_job(job_id: str, in_path: Path, original_name: str,
                     page_limit: Optional[int], settings: Settings,
                     job_store: JobStore, storage: Storage) -> None:
    """Execute one PDF scan job to completion, pushing progress events.

    Never raises: failures are reported through the ``error`` event (the
    client-facing message) while the full traceback goes to the log.
    """
    started = time.time()
    logger.info("pdf job start job_id=%s file=%s", job_id, original_name)

    def emit(event: dict) -> None:
        job_store.push(job_id, event)

    try:
        out_name = f"scanned_{uuid.uuid4().hex[:8]}.pdf"
        out_path = storage.write_path(out_name)
        pdf_scan_service.scan_pdf_streaming(
            str(in_path), str(out_path), page_limit, settings, on_event=emit,
        )
        elapsed = round(time.time() - started, 1)
        logger.info("pdf job done job_id=%s elapsed=%.2fs output=%s",
                    job_id, time.time() - started, out_name)
        emit(events.done(out_name, elapsed))
    except Exception as exc:  # noqa: BLE001 - reported to the client as-is
        logger.exception("pdf job failed job_id=%s file=%s error=%s",
                         job_id, original_name, exc)
        emit(events.error(str(exc)))
    finally:
        storage.delete(in_path.name)
        # Always close the stream, success or failure.
        emit(events.eof())
        logger.info("pdf job finished job_id=%s elapsed=%.2fs",
                    job_id, time.time() - started)


def start_pdf_scan_job(job_id: str, in_path: Path, original_name: str,
                       page_limit: Optional[int], settings: Settings,
                       job_store: JobStore, storage: Storage) -> threading.Thread:
    """Start ``run_pdf_scan_job`` in a daemon thread and return that thread."""
    thread = threading.Thread(
        target=run_pdf_scan_job,
        args=(job_id, in_path, original_name, page_limit, settings, job_store, storage),
        name=f"rscan-pdf-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    return thread


__all__ = ["run_pdf_scan_job", "start_pdf_scan_job"]
