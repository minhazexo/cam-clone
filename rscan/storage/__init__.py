"""Storage package — artifact persistence abstraction.

    from rscan.storage import LocalTempStorage, Storage, sanitize_name

Two modules on purpose:

    file_storage.py   the ``Storage`` interface + name sanitisation
    temp_storage.py   ``LocalTempStorage`` (filesystem-backed implementation)

The abstraction exists so scan logic never touches paths directly. On
serverless (Vercel) the filesystem is ephemeral and instances are recycled, so
read-after-write is best-effort — see ``docs/DEPLOYMENT.md``.
"""

from rscan.storage.file_storage import Storage, sanitize_name
from rscan.storage.temp_storage import LocalTempStorage

__all__ = ["Storage", "LocalTempStorage", "sanitize_name"]
