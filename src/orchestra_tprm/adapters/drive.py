from __future__ import annotations

import uuid


class FakeDriveAdapter:
    def __init__(self) -> None:
        self._folders: dict[str, list[dict]] = {}
        self._files: dict[str, bytes] = {}

    def seed_folder(self, folder_id: str, files: list[dict], contents: dict[str, bytes] | None = None) -> None:
        self._folders[folder_id] = files
        if contents:
            self._files.update(contents)

    def list_files(self, folder_id: str) -> list[dict]:
        return list(self._folders.get(folder_id, []))

    def download_file(self, file_id: str) -> bytes:
        return self._files.get(file_id, b"")
