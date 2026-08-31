"""Tests for the File Type Verifier.

The fixtures are raw bytes on purpose: the point of the tool is that it never
trusts the name, so the tests hand it headers with deliberately wrong
extensions and check the verdict, not the file.
"""
import os
import zipfile

import pytest

from conftest import needs_symlinks

from automation_tools.tools import file_type as ft

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 24
PDF = b"%PDF-1.7\n" + b"\x00" * 24
GZIP = b"\x1f\x8b\x08\x00" + b"\x00" * 24
ELF = b"\x7fELF\x02\x01\x01" + b"\x00" * 24


def _write(path, data):
    path.write_bytes(data)
    return str(path)


def _zip(path, members):
    with zipfile.ZipFile(str(path), "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return str(path)


# ── detection ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("data, expected", [
    (PNG, "png"),
    (JPEG, "jpeg"),
    (b"GIF89a" + b"\x00" * 16, "gif"),
    (PDF, "pdf"),
    (GZIP, "gzip"),
    (b"BZh9" + b"\x00" * 16, "bzip2"),
    (b"7z\xbc\xaf\x27\x1c" + b"\x00" * 16, "7z"),
    (b"SQLite format 3\x00" + b"\x00" * 16, "sqlite"),
    (b"ID3\x03" + b"\x00" * 16, "mp3"),
    (b"fLaC" + b"\x00" * 16, "flac"),
    (ELF, "elf"),
    (b"MZ\x90\x00" + b"\x00" * 16, "exe"),
    (b"#!/bin/sh\necho hi\n", "script"),
])
def test_detect_reads_the_signature(tmp_path, data, expected):
    assert ft.detect(_write(tmp_path / "sample", data)) == expected


def test_detect_reads_a_signature_that_sits_at_an_offset(tmp_path):
    # tar puts its magic 257 bytes in, well past any header-only check.
    assert ft.detect(_write(tmp_path / "a.tar", b"\x00" * 257 + b"ustar\x0000")) == "tar"


@pytest.mark.parametrize("form, expected", [(b"WEBP", "webp"), (b"WAVE", "wav"), (b"AVI ", "avi")])
def test_detect_tells_riff_containers_apart(tmp_path, form, expected):
    data = b"RIFF" + b"\x24\x00\x00\x00" + form + b"\x00" * 16
    assert ft.detect(_write(tmp_path / "riff", data)) == expected


def test_detect_looks_inside_a_zip_for_office_formats(tmp_path):
    docx = _zip(tmp_path / "a.docx", {"word/document.xml": "<w/>"})
    xlsx = _zip(tmp_path / "a.xlsx", {"xl/workbook.xml": "<x/>"})
    jar = _zip(tmp_path / "a.jar", {"META-INF/MANIFEST.MF": "Manifest-Version: 1.0"})
    plain = _zip(tmp_path / "a.zip", {"notes.txt": "hi"})
    assert ft.detect(docx) == "docx"
    assert ft.detect(xlsx) == "xlsx"
    assert ft.detect(jar) == "jar"
    assert ft.detect(plain) == "zip"


def test_detect_reads_the_odf_mimetype_member(tmp_path):
    odt = _zip(tmp_path / "a.odt",
               {"mimetype": "application/vnd.oasis.opendocument.text"})
    epub = _zip(tmp_path / "a.epub", {"mimetype": "application/epub+zip"})
    assert ft.detect(odt) == "odt"
    assert ft.detect(epub) == "epub"


def test_detect_falls_back_to_zip_when_the_archive_is_broken(tmp_path):
    # A truncated OOXML still starts with PK; that is all we can honestly say.
    broken = _write(tmp_path / "cut.docx", b"PK\x03\x04" + b"\x00" * 20)
    assert ft.detect(broken) == "zip"


def test_detect_returns_none_for_plain_text_and_empty_files(tmp_path):
    assert ft.detect(_write(tmp_path / "notes.txt", b"just some prose\n")) is None
    assert ft.detect(_write(tmp_path / "empty.bin", b"")) is None


def test_detect_returns_none_when_the_file_cannot_be_read(tmp_path):
    assert ft.detect(str(tmp_path / "missing.png")) is None


# ── verdicts ────────────────────────────────────────────────────────────────
def test_matching_extension_is_ok(tmp_path):
    verdict = ft.verify(_write(tmp_path / "photo.PNG", PNG))
    assert (verdict.status, verdict.detected, verdict.extension) == (ft.OK, "png", ".png")


def test_a_png_called_pdf_is_a_mismatch(tmp_path):
    verdict = ft.verify(_write(tmp_path / "report.pdf", PNG))
    assert verdict.status == ft.MISMATCH
    assert verdict.detected == "png"
    assert verdict.suggestion == ".png"


def test_a_known_format_under_an_unclaimed_extension_is_only_unnamed(tmp_path):
    # Odd, not a lie: nothing else claims .dat, so there is nothing to contradict.
    verdict = ft.verify(_write(tmp_path / "blob.dat", PNG))
    assert verdict.status == ft.UNNAMED


def test_a_file_with_no_signature_is_unknown_not_a_failure(tmp_path):
    verdict = ft.verify(_write(tmp_path / "notes.txt", b"hello\n"))
    assert (verdict.status, verdict.detected, verdict.suggestion) == (ft.UNKNOWN, None, "")


def test_an_extensionless_binary_is_accepted_when_the_format_allows_it(tmp_path):
    assert ft.verify(_write(tmp_path / "a.out", ELF)).status == ft.UNNAMED
    assert ft.verify(_write(tmp_path / "binary", ELF)).status == ft.OK


def test_an_alternate_extension_still_matches(tmp_path):
    assert ft.verify(_write(tmp_path / "p.jpeg", JPEG)).status == ft.OK
    assert ft.verify(_write(tmp_path / "p.jpg", JPEG)).status == ft.OK


# ── scanning ────────────────────────────────────────────────────────────────
def test_scan_accepts_a_single_file(tmp_path):
    verdicts = ft.scan(_write(tmp_path / "photo.png", PNG))
    assert [v.status for v in verdicts] == [ft.OK]


def test_scan_walks_subfolders(tmp_path):
    (tmp_path / "sub").mkdir()
    _write(tmp_path / "a.png", PNG)
    _write(tmp_path / "sub" / "b.pdf", PNG)
    assert {os.path.basename(v.path) for v in ft.scan(str(tmp_path))} == {"a.png", "b.pdf"}


def test_scan_respects_no_recursive(tmp_path):
    (tmp_path / "sub").mkdir()
    _write(tmp_path / "a.png", PNG)
    _write(tmp_path / "sub" / "b.png", PNG)
    assert [os.path.basename(v.path) for v in ft.scan(str(tmp_path), recursive=False)] == ["a.png"]


def test_scan_skips_default_and_custom_excludes(tmp_path):
    (tmp_path / "__pycache__").mkdir()
    _write(tmp_path / "__pycache__" / "cached.pdf", PNG)
    _write(tmp_path / "keep.png", PNG)
    _write(tmp_path / "scratch.tmp", PNG)
    names = {os.path.basename(v.path) for v in ft.scan(str(tmp_path), excludes=["*.tmp"])}
    assert names == {"keep.png"}


@needs_symlinks
def test_scan_ignores_symlinks(tmp_path):
    target = _write(tmp_path / "real.png", PNG)
    os.symlink(target, str(tmp_path / "link.png"))
    assert [os.path.basename(v.path) for v in ft.scan(str(tmp_path))] == ["real.png"]


# ── entry point ─────────────────────────────────────────────────────────────
def test_run_fails_when_an_extension_contradicts_the_content(tmp_path):
    _write(tmp_path / "invoice.pdf", PNG)
    assert ft.run_file_type_check(str(tmp_path)) is False


def test_run_succeeds_on_a_clean_folder(tmp_path):
    _write(tmp_path / "a.png", PNG)
    _write(tmp_path / "b.jpg", JPEG)
    _write(tmp_path / "notes.txt", b"prose\n")
    assert ft.run_file_type_check(str(tmp_path)) is True


def test_run_does_not_fail_on_unnamed_or_unknown_files(tmp_path):
    _write(tmp_path / "blob.dat", PNG)
    _write(tmp_path / "notes.txt", b"prose\n")
    assert ft.run_file_type_check(str(tmp_path), show_unknown=True) is True


def test_run_reports_a_missing_path(tmp_path):
    assert ft.run_file_type_check(str(tmp_path / "nope")) is False


def test_run_succeeds_on_an_empty_folder(tmp_path):
    assert ft.run_file_type_check(str(tmp_path)) is True


def test_run_exports_every_verdict_to_csv(tmp_path):
    _write(tmp_path / "invoice.pdf", PNG)
    _write(tmp_path / "notes.txt", b"prose\n")
    report = tmp_path / "report.csv"

    assert ft.run_file_type_check(str(tmp_path), export_path=str(report)) is False
    lines = report.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "status,extension,detected,suggested_extension,path"
    assert any(line.startswith("mismatch,.pdf,png,.png,") for line in lines)
    assert any(line.startswith("unknown,.txt,,,") for line in lines)


def test_export_survives_an_unwritable_destination(tmp_path):
    verdicts = [ft.verify(_write(tmp_path / "a.png", PNG))]
    ft.export_verdicts(verdicts, str(tmp_path / "missing" / "report.csv"))
