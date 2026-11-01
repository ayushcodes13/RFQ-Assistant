"""Adversarial path-containment checks for document storage."""

import hashlib

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
    case_dir = storage._case_directory("RFQ-SAFE")
    case_dir.mkdir()
    disk_name = hashlib.sha256(b"linked.txt").hexdigest()
    (case_dir / disk_name).symlink_to(outside)

    assert storage.get_file("RFQ-SAFE", "linked.txt") is None
    with pytest.raises(ValueError, match="Path traversal blocked"):
        storage.save_file("RFQ-SAFE", "linked.txt", b"replace")
    assert outside.read_bytes() == b"private"


def test_storage_rejects_symlinks_that_redirect_inside_upload_tree(tmp_path):
    storage = DocumentStorage(tmp_path / "storage")
    storage.save_file("RFQ-OTHER", "private.txt", b"other case")
    target_case = storage._case_directory("RFQ-OTHER")
    target_file = storage._file_in_case(target_case, "private.txt")

    linked_case = storage.uploads_dir / storage._case_directory("RFQ-LINKED").name
    linked_case.symlink_to(target_case, target_is_directory=True)
    assert storage.get_file("RFQ-LINKED", "private.txt") is None
    assert storage.delete_case("RFQ-LINKED") is False

    linked_case.unlink()
    linked_case.mkdir()
    linked_file = storage._file_in_case(linked_case, "private.txt")
    linked_file.symlink_to(target_file)
    assert storage.get_file("RFQ-LINKED", "private.txt") is None
    with pytest.raises(ValueError, match="Path traversal blocked"):
        storage.save_file("RFQ-LINKED", "private.txt", b"overwrite")
    assert target_file.read_bytes() == b"other case"


def test_delete_case_does_not_follow_a_case_directory_symlink(tmp_path):
    storage = DocumentStorage(tmp_path / "storage")
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")
    storage._case_directory("RFQ-SYMLINK").symlink_to(outside, target_is_directory=True)

    assert storage.delete_case("RFQ-SYMLINK") is False
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_storage_migrates_legacy_case_and_filename_paths(tmp_path):
    uploads = tmp_path / "storage" / "uploads"
    old_case = uploads / "RFQ-LEGACY"
    old_case.mkdir(parents=True)
    original = b"synthetic legacy RFQ source"
    (old_case / "buyer_request.pdf").write_bytes(original)

    storage = DocumentStorage(tmp_path / "storage")

    assert storage.get_file("RFQ-LEGACY", "buyer_request.pdf") == original
    assert not old_case.exists()
    assert storage.get_path("RFQ-LEGACY", "buyer_request.pdf") is not None


def test_legacy_migration_does_not_follow_symlinked_sources(tmp_path):
    uploads = tmp_path / "storage" / "uploads"
    old_case = uploads / "RFQ-LEGACY-LINK"
    old_case.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("preserve", encoding="utf-8")
    (old_case / "linked.txt").symlink_to(outside)

    storage = DocumentStorage(tmp_path / "storage")

    assert outside.read_text(encoding="utf-8") == "preserve"
    assert (old_case / "linked.txt").is_symlink()
    assert storage.get_file("RFQ-LEGACY-LINK", "linked.txt") is None
