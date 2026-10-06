"""Service layer — use-cases that orchestrate domain + storage + jobs.

    from rscan.services import image_scan_service, pdf_scan_service

    image_scan_service     upload bytes -> scanned JPEG artifact
    pdf_scan_service       PDF file -> scanned PDF (sync and streaming)
    scan_progress_service  job events -> Server-Sent Events frames

Services receive their collaborators (settings, storage, job store) as
arguments; they never import Flask and never build HTTP responses. Routes
stay validate -> call service -> respond.
"""

from rscan.services import image_scan_service, pdf_scan_service, scan_progress_service

__all__ = ["image_scan_service", "pdf_scan_service", "scan_progress_service"]
