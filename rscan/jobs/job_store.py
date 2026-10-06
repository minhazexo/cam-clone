"""In-memory job store for SSE scan progress.

Why in-memory: the server PDF flow starts a background thread in the same
process that serves the SSE stream, so a queue object is all the coordination
needed. Consequences (documented in ``docs/DEPLOYMENT.md``):

    * one Vercel instance == one job namespace; a progress request that lands
      on another instance sees ``JobNotFoundError``;
    * process restart drops jobs (the client re-scans, which is cheap).

Thread safety: every mutation happens under one ``threading.Lock``; the SSE
generator reads the queue object once, outside the lock, and blocks on it.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class Job:
    """One background PDF scan.

    ``queue`` carries JSON strings ready for ``data: <payload>`` SSE framing.
    """

    id: str
    queue: "queue.Queue[str]" = field(default_factory=queue.Queue)
    created_at: float = field(default_factory=time.time)


class JobStore:
    """Tracks scan jobs and their progress queues for one process."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = ttl_seconds
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------
    def create(self) -> Job:
        """Register a new job and return it (id is a uuid4 hex string)."""
        job = Job(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        """Return the job with ``job_id`` or None when unknown/expired."""
        with self._lock:
            return self._jobs.get(job_id)

    def push(self, job_id: str, event: dict) -> None:
        """Append one progress event to a job's queue (no-op if expired)."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            job.queue.put(json.dumps(event))

    def delete(self, job_id: str) -> None:
        """Forget a job without touching its artifacts."""
        with self._lock:
            self._jobs.pop(job_id, None)

    def cleanup(self) -> int:
        """Drop jobs older than ``ttl_seconds``; returns how many were dropped."""
        now = time.time()
        with self._lock:
            stale = [jid for jid, job in self._jobs.items()
                     if now - job.created_at > self.ttl_seconds]
            for jid in stale:
                del self._jobs[jid]
        if stale:
            logger.info("job store cleanup removed=%d remaining=%d",
                        len(stale), len(self._jobs))
        return len(stale)

    # -- introspection (tests, health) ------------------------------------
    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)


def drain(job: Job) -> list:
    """Non-blocking drain of a job's queue into parsed dicts (used by tests)."""
    drained = []
    while True:
        try:
            drained.append(json.loads(job.queue.get_nowait()))
        except queue.Empty:
            return drained


__all__ = ["Job", "JobStore", "drain"]
