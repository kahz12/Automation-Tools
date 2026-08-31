import argparse
import os
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from rich.table import Table

from automation_tools.core import fs

from automation_tools.core.report import export_rows
from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)

# Checks that a file really is what its extension claims.
#
# An extension is just the end of a name: anyone can rename `payload.exe` to
# `photo.jpg`, and a download that silently returned an HTML error page still
# lands on disk as `report.pdf`. This reads the first bytes instead, where most
# formats write a fixed signature ("magic number"), and compares what it finds
# against what the name promises.
#
# Everything is standard library, so there is no libmagic and no `file` binary
# to install; it behaves the same on Termux, Linux and Windows.
#
# What a verdict means:
#   ok         signature matches the extension.
#   mismatch   signature says one thing, the extension says another. The
#              interesting case, and the only one that fails the run.
#   unnamed    a recognised format under an extension we have no rule for
#              (a PNG called .dat). Worth a look, not an error.
#   unknown    no signature matched. Most text formats (.txt, .csv, .md, .py)
#              have none at all, so this is silence, not suspicion.

DEFAULT_EXCLUDES = list(fs.DEFAULT_EXCLUDES)

# How many bytes to read. One tar block: tar writes its magic 257 bytes in, so
# anything shorter silently stops recognising tarballs, and every other
# signature below sits comfortably inside the first few bytes.
_HEADER_BYTES = 512

# (type name, offset, signature). Order matters only where one prefix could
# shadow another; longer and more specific entries come first.
_SIGNATURES: Tuple[Tuple[str, int, bytes], ...] = (
    ("png",    0, b"\x89PNG\r\n\x1a\n"),
    ("jpeg",   0, b"\xff\xd8\xff"),
    ("gif",    0, b"GIF87a"),
    ("gif",    0, b"GIF89a"),
    ("bmp",    0, b"BM"),
    ("tiff",   0, b"II*\x00"),
    ("tiff",   0, b"MM\x00*"),
    ("ico",    0, b"\x00\x00\x01\x00"),
    ("psd",    0, b"8BPS"),
    ("pdf",    0, b"%PDF-"),
    ("ps",     0, b"%!PS"),
    ("rtf",    0, b"{\\rtf"),
    ("sqlite", 0, b"SQLite format 3\x00"),
    ("gzip",   0, b"\x1f\x8b"),
    ("bzip2",  0, b"BZh"),
    ("xz",     0, b"\xfd7zXZ\x00"),
    ("zstd",   0, b"\x28\xb5\x2f\xfd"),
    ("7z",     0, b"7z\xbc\xaf\x27\x1c"),
    ("rar",    0, b"Rar!\x1a\x07"),
    ("tar",  257, b"ustar"),
    ("zip",    0, b"PK\x03\x04"),
    ("zip",    0, b"PK\x05\x06"),   # empty archive
    ("flac",   0, b"fLaC"),
    ("ogg",    0, b"OggS"),
    ("mp3",    0, b"ID3"),
    ("mp3",    0, b"\xff\xfb"),
    ("mp3",    0, b"\xff\xf3"),
    ("mp4",    4, b"ftyp"),
    ("matroska", 0, b"\x1a\x45\xdf\xa3"),
    ("elf",    0, b"\x7fELF"),
    ("exe",    0, b"MZ"),
    ("class",  0, b"\xca\xfe\xba\xbe"),
    ("wasm",   0, b"\x00asm"),
    ("script", 0, b"#!"),
)

# RIFF containers all start the same way and name themselves at offset 8.
_RIFF_FORMS = {b"WEBP": "webp", b"WAVE": "wav", b"AVI ": "avi"}

# Inside a zip, these members identify the real format.
_ZIP_MEMBERS: Tuple[Tuple[str, str], ...] = (
    ("word/document.xml", "docx"),
    ("xl/workbook.xml", "xlsx"),
    ("ppt/presentation.xml", "pptx"),
    ("AndroidManifest.xml", "apk"),
    ("META-INF/MANIFEST.MF", "jar"),
)
_ODF_MIMETYPES: Tuple[Tuple[bytes, str], ...] = (
    (b"application/vnd.oasis.opendocument.text", "odt"),
    (b"application/vnd.oasis.opendocument.spreadsheet", "ods"),
    (b"application/vnd.oasis.opendocument.presentation", "odp"),
    (b"application/epub+zip", "epub"),
)

# Which extensions each detected type legitimately answers to.
_EXPECTED: Dict[str, Tuple[str, ...]] = {
    "png": (".png",),
    "jpeg": (".jpg", ".jpeg", ".jpe", ".jfif"),
    "gif": (".gif",),
    "bmp": (".bmp", ".dib"),
    "tiff": (".tif", ".tiff"),
    "webp": (".webp",),
    "ico": (".ico", ".cur"),
    "psd": (".psd",),
    "pdf": (".pdf",),
    "ps": (".ps", ".eps"),
    "rtf": (".rtf",),
    "sqlite": (".sqlite", ".sqlite3", ".db"),
    "gzip": (".gz", ".tgz", ".gzip"),
    "bzip2": (".bz2", ".tbz2"),
    "xz": (".xz", ".txz"),
    "zstd": (".zst",),
    "7z": (".7z",),
    "rar": (".rar",),
    "tar": (".tar",),
    "zip": (".zip",),
    "docx": (".docx", ".docm"),
    "xlsx": (".xlsx", ".xlsm"),
    "pptx": (".pptx", ".pptm"),
    "odt": (".odt",),
    "ods": (".ods",),
    "odp": (".odp",),
    "epub": (".epub",),
    "apk": (".apk",),
    "jar": (".jar",),
    "flac": (".flac",),
    "ogg": (".ogg", ".oga", ".ogv", ".opus"),
    "mp3": (".mp3",),
    "mp4": (".mp4", ".m4a", ".m4v", ".mov", ".3gp"),
    "matroska": (".mkv", ".webm", ".mka"),
    "elf": (".so", ".o", ".elf", ".bin", ""),
    "exe": (".exe", ".dll", ".sys", ".scr"),
    "class": (".class",),
    "wasm": (".wasm",),
    "script": (".sh", ".bash", ".py", ".pl", ".rb", ".zsh", ""),
}

OK = "ok"
MISMATCH = "mismatch"
UNNAMED = "unnamed"
UNKNOWN = "unknown"


@dataclass
class Verdict:
    """What one file turned out to be."""
    path: str
    extension: str
    detected: Optional[str]
    status: str

    @property
    def suggestion(self) -> str:
        """The extension this content would normally carry."""
        if self.detected and self.detected in _EXPECTED:
            for candidate in _EXPECTED[self.detected]:
                if candidate:
                    return candidate
        return ""


# ── Detection ────────────────────────────────────────────────────────────────
def _zip_kind(path: str) -> str:
    """Looks inside a zip to tell docx/xlsx/odt/apk apart from a plain archive."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            for member, kind in _ZIP_MEMBERS:
                if member in names:
                    return kind
            if "mimetype" in names:
                mimetype = archive.read("mimetype")[:64]
                for prefix, kind in _ODF_MIMETYPES:
                    if mimetype.startswith(prefix):
                        return kind
    except Exception:
        # Truncated or encrypted: the PK header is still all we can honestly say.
        pass
    return "zip"


def detect(path: str) -> Optional[str]:
    """The format a file's own bytes say it is, or None when nothing matches."""
    try:
        with open(path, "rb") as handle:
            header = handle.read(_HEADER_BYTES)
    except OSError:
        return None
    if not header:
        return None

    if header[:4] == b"RIFF" and len(header) >= 12:
        form = _RIFF_FORMS.get(header[8:12])
        if form:
            return form

    for kind, offset, signature in _SIGNATURES:
        if header[offset:offset + len(signature)] == signature:
            return _zip_kind(path) if kind == "zip" else kind
    return None


def verify(path: str) -> Verdict:
    """Compares a file's signature against the extension it carries."""
    extension = os.path.splitext(path)[1].lower()
    detected = detect(path)

    if detected is None:
        return Verdict(path, extension, None, UNKNOWN)
    expected = _EXPECTED.get(detected, ())
    if extension in expected:
        return Verdict(path, extension, detected, OK)
    # An extension nobody claims is a loose end, not a lie: a PNG named .dat is
    # odd but harmless, while a PNG named .pdf is the thing worth flagging.
    claimed_by_someone = any(extension in exts for exts in _EXPECTED.values())
    status = MISMATCH if claimed_by_someone else UNNAMED
    return Verdict(path, extension, detected, status)


# ── Scanning ─────────────────────────────────────────────────────────────────
def scan(path: str, recursive: bool = True,
         excludes: Optional[List[str]] = None) -> List[Verdict]:
    """Verifies one file, or every file under a folder."""
    patterns = list(DEFAULT_EXCLUDES) + list(excludes or [])
    return [verify(full) for full in fs.walk_files(
        path, recursive=recursive, excludes=patterns)]


# ── Reporting ────────────────────────────────────────────────────────────────
def _print_mismatches(verdicts: List[Verdict], limit: int = 40) -> None:
    rows = [v for v in verdicts if v.status == MISMATCH]
    if not rows:
        return
    table = Table(
        title="Extension does not match the content",
        header_style="bold cyan", title_style="bold red",
    )
    table.add_column("Named", width=10)
    table.add_column("Actually", width=10, style="yellow")
    table.add_column("Should be", width=10, style="green")
    table.add_column("Path", overflow="fold")
    for verdict in rows[:limit]:
        table.add_row(
            verdict.extension or "(none)",
            verdict.detected or "?",
            verdict.suggestion or "?",
            verdict.path,
        )
    console.print(table)
    if len(rows) > limit:
        console.print(f"[dim]... and {len(rows) - limit} more (hidden).[/dim]")


def _print_unnamed(verdicts: List[Verdict], limit: int = 20) -> None:
    rows = [v for v in verdicts if v.status == UNNAMED]
    if not rows:
        return
    console.print("\n[bold yellow]Recognised content under an unusual extension:[/bold yellow]")
    for verdict in rows[:limit]:
        named = verdict.extension or "(no extension)"
        console.print(f"  [yellow]•[/yellow] {verdict.path}  [dim]{named} → looks like {verdict.detected}[/dim]")
    if len(rows) > limit:
        console.print(f"[dim]  ... and {len(rows) - limit} more.[/dim]")


def export_verdicts(verdicts: List[Verdict], out_path: str) -> bool:
    """Writes every verdict to `out_path` as CSV."""
    return export_rows(
        out_path,
        ["status", "extension", "detected", "suggested_extension", "path"],
        ([v.status, v.extension, v.detected or "", v.suggestion, v.path] for v in verdicts),
    )


# ── Entry point ──────────────────────────────────────────────────────────────
def run_file_type_check(
    path: str,
    recursive: bool = True,
    excludes: Optional[List[str]] = None,
    export_path: Optional[str] = None,
    show_unknown: bool = False,
) -> bool:
    """Verifies a file or folder against known magic numbers.

    Returns False when at least one extension contradicts its content, so the
    exit code carries the verdict. Files with no known signature are not a
    failure: most text formats have none.
    """
    if not os.path.exists(path):
        print_error(f"The path '{path}' does not exist.")
        return False

    print_step(f"Checking [bold]{path}[/bold] against known signatures…")
    verdicts = scan(path, recursive=recursive, excludes=excludes)
    if not verdicts:
        print_warning("No files to check.")
        return True

    counts = {status: 0 for status in (OK, MISMATCH, UNNAMED, UNKNOWN)}
    for verdict in verdicts:
        counts[verdict.status] += 1

    summary = Table(title="File type report", header_style="bold cyan")
    summary.add_column("Result")
    summary.add_column("Files", justify="right")
    summary.add_row("[green]✓ Matches its extension[/green]", str(counts[OK]))
    summary.add_row("[red]✗ Extension is wrong[/red]", str(counts[MISMATCH]))
    summary.add_row("[yellow]? Unusual extension[/yellow]", str(counts[UNNAMED]))
    summary.add_row("[dim]· No known signature[/dim]", str(counts[UNKNOWN]))
    console.print(summary)

    _print_mismatches(verdicts)
    _print_unnamed(verdicts)

    if show_unknown:
        unknown = [v for v in verdicts if v.status == UNKNOWN]
        if unknown:
            console.print("\n[dim]No signature to check against (normal for text files):[/dim]")
            for verdict in unknown[:40]:
                console.print(f"  [dim]· {verdict.path}[/dim]")
            if len(unknown) > 40:
                console.print(f"[dim]  ... and {len(unknown) - 40} more.[/dim]")

    if export_path:
        export_verdicts(verdicts, export_path)

    if counts[MISMATCH]:
        print_error(
            f"{counts[MISMATCH]} file(s) do not match their extension. "
            "Renaming one to its real type is safe; opening it is not, until you know why."
        )
        return False

    print_success(f"No mismatches. {counts[OK]} file(s) verified against a known signature.")
    if counts[UNKNOWN]:
        console.print(
            f"[dim]{counts[UNKNOWN]} file(s) carry no signature to check "
            "(text, source code and similar).[/dim]"
        )
    return True


def main() -> None:
    """CLI entry point for the File Type Verifier."""
    parser = argparse.ArgumentParser(
        description="Check that files really are what their extension claims."
    )
    parser.add_argument("path", help="File or folder to check.")
    parser.add_argument("--no-recursive", action="store_true", help="Do not recurse into subfolders.")
    parser.add_argument(
        "-x", "--exclude", nargs="*", default=[],
        help="Glob patterns to skip (e.g. '*.tmp').",
    )
    parser.add_argument("--export", help="Write a CSV report to this path.")
    parser.add_argument(
        "--show-unknown", action="store_true",
        help="Also list files with no known signature.",
    )
    args = parser.parse_args()

    ok = run_file_type_check(
        path=args.path,
        recursive=not args.no_recursive,
        excludes=args.exclude,
        export_path=args.export,
        show_unknown=args.show_unknown,
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
