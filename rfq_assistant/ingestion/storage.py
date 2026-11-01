"""Local file persistence for original RFQ documents and digests."""

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

_SAFE_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SAFE_STORED_NAME = re.compile(r"[\w][\w.-]{0,254}\Z", re.UNICODE)
_HASHED_COMPONENT = re.compile(r"[0-9a-f]{64}\Z")
log = logging.getLogger(__name__)


class DocumentStorage:
    """Manages secure local persistence of uploaded RFQ documents."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            base_dir = Path("storage")
        self.base_dir = base_dir
        self.uploads_dir = self.base_dir / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_paths()

    def _migrate_legacy_paths(self) -> None:
        """Move pre-hash case/file names into opaque storage paths once.

        Older versions stored case IDs and sanitized filenames directly in the
        uploads tree. The migration only moves regular files from safe legacy
        directories and never follows symlinks. New hashed directories are
        already in the destination layout and are left untouched.
        """
        root = self.uploads_dir.resolve()
        for legacy_case_dir in self.uploads_dir.iterdir():
            case_id = legacy_case_dir.name
            if (
                legacy_case_dir.is_symlink()
                or not legacy_case_dir.is_dir()
                or _HASHED_COMPONENT.fullmatch(case_id)
                or not _SAFE_CASE_ID.fullmatch(case_id)
            ):
                continue

            disk_case_id = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
            destination_path = self.uploads_dir / disk_case_id
            if destination_path.is_symlink():
                continue
            destination = destination_path.resolve()
            try:
                destination.relative_to(root)
            except ValueError:
                continue
            if destination.is_symlink():
                continue
            destination.mkdir(parents=True, exist_ok=True)

            for legacy_file in legacy_case_dir.iterdir():
                filename = legacy_file.name
                if (
                    legacy_file.is_symlink()
                    or not legacy_file.is_file()
                    or not _SAFE_STORED_NAME.fullmatch(filename)
                    or filename in {".", ".."}
                ):
                    continue
                disk_filename = hashlib.sha256(filename.encode("utf-8")).hexdigest()
                target = destination / disk_filename
                try:
                    target.relative_to(destination)
                    if target.is_symlink():
                        continue
                    if target.exists():
                        if target.is_file() and target.read_bytes() == legacy_file.read_bytes():
                            legacy_file.unlink()
                        continue
                    legacy_file.replace(target)
                except OSError:
                    # Preserve the original file if it cannot be moved safely.
                    log.warning("Legacy RFQ source path migration skipped a file.")

            try:
                legacy_case_dir.rmdir()
            except OSError:
                # Unknown entries remain untouched for manual recovery.
                log.warning("Legacy RFQ source path migration left an unrecognized directory.")

    def _case_directory(self, case_id: str) -> Path:
        if not _SAFE_CASE_ID.fullmatch(case_id):
            raise ValueError("Case ID contains unsafe path characters for uploads storage.")
        # Hash logical identifiers so user-controlled text never becomes a path
        # component. Keep the mapping deterministic for restart compatibility.
        disk_case_id = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
        candidate_path = self.uploads_dir / disk_case_id
        if candidate_path.is_symlink():
            raise ValueError("Case storage path cannot be a symbolic link.")
        candidate = candidate_path.resolve()
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
        candidate_path = case_dir / disk_filename
        if candidate_path.is_symlink():
            raise ValueError(f"Path traversal blocked for filename: {filename}")
        candidate = candidate_path.resolve()
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
