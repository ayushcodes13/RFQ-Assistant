"""Adversarial path-containment checks for document storage."""

import pytest

from rfq_assistant.ingestion.storage import DocumentStorage


def test_storage_rejects_traversal_for_write_read_and_delete(tmp_path):
    storage = DocumentStorage(tmp_path / "storage")

    with pytest.raises(ValueError, match="Path traversal blocked"):
        storage.save_file("RFQ-SAFE", "../../outside.txt", b"synthetic")
    assert storage.get_file("RFQ-SAFE", "../../outside.txt") is None
    assert storage.get_file("../../outside", "file.txt") is None
    assert storage.delete_case("../../outside") is False
    with pytest.raises(ValueError, match="uploads"):
        storage.save_file("../../outside", "file.txt", b"synthetic")


def test_storage_rejects_symlink_escape_on_read_and_write(tmp_path):
    storage = DocumentStorage(tmp_path / "storage")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"private")
    case_dir = storage.uploads_dir / "RFQ-SAFE"
    case_dir.mkdir()
    (case_dir / "linked.txt").symlink_to(outside)

    assert storage.get_file("RFQ-SAFE", "linked.txt") is None
    with pytest.raises(ValueError, match="Path traversal blocked"):
        storage.save_file("RFQ-SAFE", "linked.txt", b"replace")
    assert outside.read_bytes() == b"private"


def test_delete_case_does_not_follow_a_case_directory_symlink(tmp_path):
    storage = DocumentStorage(tmp_path / "storage")
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")
    (storage.uploads_dir / "RFQ-SYMLINK").symlink_to(outside, target_is_directory=True)

    assert storage.delete_case("RFQ-SYMLINK") is False
    assert marker.read_text(encoding="utf-8") == "preserve"
