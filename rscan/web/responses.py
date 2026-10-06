"""Response helpers so every API route answers in the same shape.

Success payloads are the feature payload plus optional metadata
(``{"pages": [...]}``, ``{"pdf": "scanned_ab12.pdf"}``, ``{"job_id": "..."}``);
errors are always ``{"error": "<public message>"}`` with the matching status.
Keeping the two in one module is what makes the contract easy to document and
test — see ``docs/API.md``.
"""

from __future__ import annotations

from typing import Any

from flask import jsonify


def json_ok(**payload: Any):
    """Return a 200 JSON response with the given payload."""
    return jsonify(**payload)


def json_error(message: str, status: int = 400):
    """Return ``{"error": message}`` with an explicit status code."""
    return jsonify(error=message), status


__all__ = ["json_ok", "json_error"]
