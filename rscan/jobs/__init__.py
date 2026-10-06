"""Jobs package — in-memory scan job state and its background worker.

    from rscan.jobs import JobStore, start_pdf_scan_job, events

Three modules, three responsibilities:

    events.py       the progress event vocabulary (one constructor per type)
    job_store.py    job lifecycle state (create/get/push/cleanup) + locking
    job_worker.py   runs the PDF scan in a daemon thread and reports events

The SSE endpoint never scans anything: it only translates the events a job
already produced into ``text/event-stream`` frames
(``rscan.services.scan_progress_service``). See ``docs/ARCHITECTURE.md`` for
the full job lifecycle.
"""

from rscan.jobs import events
from rscan.jobs.job_store import Job, JobStore
from rscan.jobs.job_worker import start_pdf_scan_job

__all__ = ["events", "Job", "JobStore", "start_pdf_scan_job"]
