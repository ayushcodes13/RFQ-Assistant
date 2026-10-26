"""Local file persistence for original RFQ documents and digests."""

from pathlib import Path
from typing import Optional


class DocumentStorage:
    """Manages secure local persistence of uploaded RFQ documents."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            base_dir = Path("storage")
        self.base_dir = base_dir
        self.uploads_dir = self.base_dir / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, case_id: str, filename: str, content: bytes) -> Path:
        """Saves file under case directory and returns stored path."""
        case_dir = self.uploads_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        file_path = case_dir / filename
        file_path.write_bytes(content)
        return file_path

    def get_file(self, case_id: str, filename: str) -> Optional[bytes]:
        """Reads file bytes if it exists."""
        file_path = self.uploads_dir / case_id / filename
        if file_path.exists():
            return file_path.read_bytes()
        return None

    def delete_case(self, case_id: str) -> bool:
        """Deletes all stored documents for a case."""
        case_dir = self.uploads_dir / case_id
        if case_dir.exists():
            for child in case_dir.iterdir():
                if child.is_file():
                    child.unlink()
            case_dir.rmdir()
            return True
        return False
