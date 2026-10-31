"""Bounded conversion of legacy BIFF `.xls` files to the XLSX parser format."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path


MAX_CONVERTED_XLSX_BYTES = 10 * 1024 * 1024
MAX_CONVERTED_XLSX_EXPANDED_BYTES = 50 * 1024 * 1024
XLS_CONVERSION_TIMEOUT_SECONDS = 30
_MACRO_DISABLED_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
    <prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
  </item>
</oor:items>
"""


class LegacyXLSConversionError(ValueError):
    """The legacy workbook could not be converted within its safety bounds."""


def convert_legacy_xls(content: bytes, *, converter: str | None = None) -> bytes:
    """Convert `.xls` bytes with headless LibreOffice using isolated temp state.

    The subprocess receives a reduced environment (in particular, no model API
    credentials), uses an isolated user profile, has a hard timeout, and its
    output is checked as a bounded macro-free XLSX archive before parsing.
    """
    if len(content) > MAX_CONVERTED_XLSX_BYTES:
        raise LegacyXLSConversionError("Legacy workbook exceeds the upload size limit.")
    executable = converter or shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        raise LegacyXLSConversionError(
            "Legacy .xls conversion is unavailable because LibreOffice is not installed."
        )

    with tempfile.TemporaryDirectory(prefix="rfq-xls-") as temp_root:
        root = Path(temp_root)
        source = root / "source.xls"
        output_dir = root / "converted"
        profile_dir = root / "profile"
        home_dir = root / "home"
        output_dir.mkdir()
        home_dir.mkdir()
        (profile_dir / "user").mkdir(parents=True)
        (profile_dir / "user" / "registrymodifications.xcu").write_text(
            _MACRO_DISABLED_PROFILE,
            encoding="utf-8",
        )
        source.write_bytes(content)

        environment = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home_dir),
            "TMPDIR": str(root),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        command = [
            executable,
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(output_dir),
            str(source),
        ]
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=XLS_CONVERSION_TIMEOUT_SECONDS,
                check=False,
                env=environment,
                cwd=root,
            )
        except subprocess.TimeoutExpired as exc:
            raise LegacyXLSConversionError(
                "Legacy .xls conversion exceeded its 30-second time limit."
            ) from exc
        except OSError as exc:
            raise LegacyXLSConversionError("LibreOffice could not be started for .xls conversion.") from exc

        converted = output_dir / "source.xlsx"
        if result.returncode != 0 or not converted.is_file():
            # Converter output can include source-derived text. Avoid copying it
            # into logs/errors; expose only the safe failure category.
            raise LegacyXLSConversionError("LibreOffice could not convert this .xls workbook.")
        if converted.stat().st_size > MAX_CONVERTED_XLSX_BYTES:
            raise LegacyXLSConversionError("Converted workbook exceeds the 10 MB processing limit.")

        converted_bytes = converted.read_bytes()
        _validate_converted_archive(converted_bytes)
        return converted_bytes


def _validate_converted_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            if any("vbaproject.bin" in item.filename.casefold() for item in members):
                raise LegacyXLSConversionError("Converted workbook contains macro content and was rejected.")
            if sum(item.file_size for item in members) > MAX_CONVERTED_XLSX_EXPANDED_BYTES:
                raise LegacyXLSConversionError("Converted workbook expands beyond the 50 MB safety limit.")
            if not any(item.filename == "xl/workbook.xml" for item in members):
                raise LegacyXLSConversionError("LibreOffice output is not a valid XLSX workbook.")
    except zipfile.BadZipFile as exc:
        raise LegacyXLSConversionError("LibreOffice output is not a valid XLSX archive.") from exc
