"""SSE translation service: job events -> ``text/event-stream`` frames.

Why this is a service and not part of the route: the route should only look up
a job and hand its queue to a generator. All framing knowledge (``data:``
prefix, blank-line termination, keepalive comments, which events are
terminal) lives here so the worker and the client can be reasoned about
independently.

Wire format (one event per frame)::

    data: {"type":"page_done","page":3,"total":10}\\n\\n

Keepalive: when a job is quiet for ``keepalive_seconds``, a comment frame
``: keepalive\\n\\n`` is sent so proxies (nginx, Vercel) do not close the
connection. Comment frames are ignored by ``EventSource``.
"""

from __future__ import annotations

import json
import logging
import queue
from typing import Iterator

from rscan.errors import JobNotFoundError
from rscan.jobs.job_store import Job, JobStore

logger = logging.getLogger(__name__)

#: SSE response headers; ``X-Accel-Buffering: no`` disables nginx buffering.
SSE_HEADERS = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}

#: Keepalive frame sent while a job produces no events.
KEEPALIVE_FRAME = ": keepalive\n\n"


def format_frame(payload: str) -> str:
    """Wrap a pre-serialised JSON payload in one SSE frame."""
    return f"data: {payload}\n\n"


def stream_job_events(job: Job, keepalive_seconds: int = 30) -> Iterator[str]:
    """Yield SSE frames for ``job`` until a terminal event is seen.

    The generator is intentionally dumb: it never inspects scan state, it only
    forwards queued payloads and stops on the terminal types. If the client
    disconnects, Flask closes the generator (GeneratorExit) and the job keeps
    running to completion — that is by design, so a refresh does not kill a
    long scan.
    """
    while True:
        try:
            payload = job.queue.get(timeout=keepalive_seconds)
        except queue.Empty:
            yield KEEPALIVE_FRAME
            continue

        yield format_frame(payload)

        try:
            event_type = json.loads(payload).get("type")
        except (TypeError, ValueError):  # pragma: no cover - internal payloads
            logger.warning("job %s produced a non-JSON payload", job.id)
            continue
        if event_type in ("done", "error", "_eof"):
            return


def stream_job(job_id: str, job_store: JobStore, keepalive_seconds: int = 30) -> Iterator[str]:
    """Look up ``job_id`` and stream its events.

    Raises:
        JobNotFoundError: for unknown or expired job ids (route maps this to
            404 ``{"error": "Job not found"}``).
    """
    job = job_store.get(job_id)
    if job is None:
        raise JobNotFoundError()
    logger.debug("sse stream opened job_id=%s", job_id)
    return stream_job_events(job, keepalive_seconds=keepalive_seconds)


__all__ = ["SSE_HEADERS", "KEEPALIVE_FRAME", "format_frame", "stream_job_events", "stream_job"]
