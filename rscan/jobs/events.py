"""Progress event vocabulary for long-running scans.

One constructor per event type keeps payload shapes stable and greppable:
the SSE client (``static/js/features/pdf-scan/pdf-progress.js``) switches on
``type``, so the strings below are part of the wire contract.

Lifecycle of a server PDF job::

    loading          input PDF is being opened / pages rendered
    detected         total page count known  {total}
    scanning         first page started       {page, total}
    page_done        one page finished        {page, total}
    assembling       writing the output PDF
    done             finished                 {pdf, elapsed}
    error            failed                   {message}
    _eof             internal: close the stream (never rendered)

``done``, ``error`` and ``_eof`` are terminal: the SSE generator stops there.
``_eof`` is deliberately prefixed with an underscore so a client that
forwards unknown events never shows it to a user.
"""

from __future__ import annotations

from typing import Any, Dict

EVENT_LOADING = "loading"
EVENT_DETECTED = "detected"
EVENT_SCANNING = "scanning"
EVENT_PAGE_DONE = "page_done"
EVENT_ASSEMBLING = "assembling"
EVENT_DONE = "done"
EVENT_ERROR = "error"
EVENT_EOF = "_eof"

#: Events that end the stream (the generator stops after yielding them).
TERMINAL_EVENTS = frozenset({EVENT_DONE, EVENT_ERROR, EVENT_EOF})

ProgressEvent = Dict[str, Any]


def loading() -> ProgressEvent:
    """Job accepted; pages are being rendered from the input PDF."""
    return {"type": EVENT_LOADING}


def detected(total: int) -> ProgressEvent:
    """Page count is known and the scan is about to start."""
    return {"type": EVENT_DETECTED, "total": total}


def scanning(page: int, total: int) -> ProgressEvent:
    """A page scan has started (page is 1-based)."""
    return {"type": EVENT_SCANNING, "page": page, "total": total}


def page_done(page: int, total: int) -> ProgressEvent:
    """``page`` of ``total`` pages finished scanning."""
    return {"type": EVENT_PAGE_DONE, "page": page, "total": total}


def assembling() -> ProgressEvent:
    """All pages are scanned; the output PDF is being written."""
    return {"type": EVENT_ASSEMBLING}


def done(pdf_name: str, elapsed: float) -> ProgressEvent:
    """Success: ``pdf_name`` is downloadable via ``/api/pdf/<pdf_name>``."""
    return {"type": EVENT_DONE, "pdf": pdf_name, "elapsed": elapsed}


def error(message: str) -> ProgressEvent:
    """Failure with a client-safe message."""
    return {"type": EVENT_ERROR, "message": message}


def eof() -> ProgressEvent:
    """Internal sentinel that tells the SSE generator to close."""
    return {"type": EVENT_EOF}


def is_terminal(event: ProgressEvent) -> bool:
    """True when the event ends the stream."""
    return event.get("type") in TERMINAL_EVENTS


__all__ = [
    "EVENT_LOADING",
    "EVENT_DETECTED",
    "EVENT_SCANNING",
    "EVENT_PAGE_DONE",
    "EVENT_ASSEMBLING",
    "EVENT_DONE",
    "EVENT_ERROR",
    "EVENT_EOF",
    "TERMINAL_EVENTS",
    "ProgressEvent",
    "loading",
    "detected",
    "scanning",
    "page_done",
    "assembling",
    "done",
    "error",
    "eof",
    "is_terminal",
]
