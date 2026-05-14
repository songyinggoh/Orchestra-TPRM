"""DriveAdapter — list Drive folder contents (metadata only).

Provides two implementations:

* ``FakeDriveAdapter`` — in-memory seedable fake used by unit/integration
  tests (no network). Preserved verbatim from the predecessor commit so
  existing tests and callers keep working.
* ``DriveAdapter`` — real Drive v3 client backed by ``google-api-python-client``
  with Application Default Credentials (ADC). Returns metadata only;
  blob download is intentionally out of scope (that's GeminiFilesAdapter's
  job — see Task 14 in the TPRM build plan).

Auth pattern matches the data-layer scaffold established in commit
``e8dfb52``: lazy ADC discovery via ``google.auth.default`` so module
import never touches credentials and the class can be instantiated in
test environments without GCP setup.

Folder IDs are passed in by callers (typically from environment variables
``DRIVE_VENDOR_FOLDER_ID`` / ``DRIVE_MA_FOLDER_ID`` resolved at a higher
layer); this adapter is intentionally environment-agnostic.
"""
from __future__ import annotations

from typing import Any


class FakeDriveAdapter:
    def __init__(self) -> None:
        self._folders: dict[str, list[dict]] = {}
        self._files: dict[str, bytes] = {}

    def seed_folder(
        self,
        folder_id: str,
        files: list[dict],
        contents: dict[str, bytes] | None = None,
    ) -> None:
        self._folders[folder_id] = files
        if contents:
            self._files.update(contents)

    def list_files(self, folder_id: str) -> list[dict]:
        return list(self._folders.get(folder_id, []))

    def download_file(self, file_id: str) -> bytes:
        return self._files.get(file_id, b"")


_DEFAULT_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
)

_METADATA_FIELDS = "files(id, name, mimeType, modifiedTime, size)"


class DriveAdapter:
    """Real Google Drive v3 adapter (metadata-only).

    Uses Application Default Credentials. Credentials and the service
    client are constructed lazily on first use so importing this module
    or instantiating the class never performs network I/O.

    Example:
        >>> adapter = DriveAdapter()
        >>> files = adapter.list_files("0AKxxxxxxxxxxxxUk9PVA")
        >>> [f["name"] for f in files]
        ['Acme_MSA_2024.pdf', 'Acme_SOC2_2024.pdf']
    """

    def __init__(self, scopes: list[str] | None = None) -> None:
        self._scopes: list[str] = list(scopes) if scopes is not None else list(_DEFAULT_SCOPES)
        self._service: Any = None

    def _get_service(self) -> Any:
        """Lazily build and cache the Drive v3 service client."""
        if self._service is None:
            # Local imports keep googleapiclient/google.auth optional at
            # import time — only required when the real adapter is used.
            from google.auth import default as google_auth_default
            from googleapiclient.discovery import build

            creds, _project = google_auth_default(scopes=self._scopes)
            self._service = build(
                "drive",
                "v3",
                credentials=creds,
                cache_discovery=False,
            )
        return self._service

    def list_files(self, folder_id: str) -> list[dict[str, str]]:
        """Return metadata for non-trashed files directly inside ``folder_id``.

        The Drive query is scoped to a single parent folder (no recursion)
        and excludes trashed files. Returns ``[]`` when the folder is
        empty or the response omits the ``files`` key.

        Args:
            folder_id: Google Drive folder ID (e.g. from
                ``DRIVE_VENDOR_FOLDER_ID``).

        Returns:
            List of file metadata dicts with keys ``id``, ``name``,
            ``mimeType``, ``modifiedTime``, ``size`` (subject to Drive's
            field availability — ``size`` is absent for Google-native
            doc types).
        """
        service = self._get_service()
        response = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields=_METADATA_FIELDS,
                pageSize=100,
            )
            .execute()
        )
        return list(response.get("files", []))
