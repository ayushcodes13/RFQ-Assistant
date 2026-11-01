"""Local file persistence for original RFQ documents and digests."""

import hashlib
import re
from pathlib import Path
from typing import Optional

_SAFE_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SAFE_STORED_NAME = re.compile(r"[\w][\w.-]{0,254}\Z", re.UNICODE)


class DocumentStorage:
    """Manages secure local persistence of uploaded RFQ documents."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            base_dir = Path("storage")
        self.base_dir = base_dir
        self.uploads_dir = self.base_dir / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def _case_directory(self, case_id: str) -> Path:
        if not _SAFE_CASE_ID.fullmatch(case_id):
            raise ValueError("Case ID contains unsafe path characters for uploads storage.")
        # Hash logical identifiers so user-controlled text never becomes a path
        # component. Keep the mapping deterministic for restart compatibility.
        disk_case_id = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
        candidate = (self.uploads_dir / disk_case_id).resolve()
        root = self.uploads_dir.resolve()
        try:
            relative = candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("Case storage path escaped the uploads directory.") from exc
        if not relative.parts:
            raise ValueError("A case ID must identify a child of the uploads directory.")
        return candidate

    @staticmethod
    def _file_in_case(case_dir: Path, filename: str) -> Path:
        if not _SAFE_STORED_NAME.fullmatch(filename) or filename in {".", ".."}:
            raise ValueError(f"Path traversal blocked for filename: {filename}")
        disk_filename = hashlib.sha256(filename.encode("utf-8")).hexdigest()
        candidate = (case_dir / disk_filename).resolve()
        try:
            relative = candidate.relative_to(case_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Path traversal blocked for filename: {filename}") from exc
        if not relative.parts:
            raise ValueError("Filename must identify a file within the case directory.")
        return candidate

    def save_file(self, case_id: str, filename: str, content: bytes) -> Path:
        """Saves file under case directory and returns stored path."""
        case_dir = self._case_directory(case_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._file_in_case(case_dir, filename)
        file_path.write_bytes(content)
        return file_path

    def get_file(self, case_id: str, filename: str) -> Optional[bytes]:
        """Reads file bytes if it exists."""
        try:
            case_dir = self._case_directory(case_id)
            file_path = self._file_in_case(case_dir, filename)
        except ValueError:
            return None
        if file_path.exists():
            return file_path.read_bytes()
        return None

    def get_path(self, case_id: str, filename: str) -> Optional[Path]:
        """Returns an existing opaque storage path for a logical filename."""
        try:
            case_dir = self._case_directory(case_id)
            file_path = self._file_in_case(case_dir, filename)
        except ValueError:
            return None
        return file_path if file_path.is_file() else None

    def delete_case(self, case_id: str) -> bool:
        """Deletes all stored documents for a case."""
        try:
            case_dir = self._case_directory(case_id)
        except ValueError:
            return False
        if case_dir.exists():
            for child in case_dir.iterdir():
                if child.is_file():
                    child.unlink()
            case_dir.rmdir()
            return True
        return False
