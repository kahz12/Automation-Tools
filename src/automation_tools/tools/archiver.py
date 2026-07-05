import argparse
import fnmatch
import os
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)
from rich.table import Table

# --- Backup / Archiver Tool ---
# Bundle files and folders into a single compressed archive (a timestamped
# backup), inspect an archive's contents, or extract one — using only the
# standard library (zipfile / tarfile), so it runs the same on Linux, Windows
# and Termux/Android with no external binaries.
#
# Safe by default:
#   - "create" and "extract" run in dry-run mode first; nothing is written until
#     you pass --apply (or toggle Apply in the menu).
#   - "extract" refuses paths that escape the destination folder (Zip Slip) and
#     skips existing files unless --overwrite is given.
#   - symbolic links are never followed, so an archive can't leak files from
#     outside the sources you chose.

# Supported archive formats → the file extension each one uses.
ARCHIVE_FORMATS = {
    "zip": ".zip",
    "tar": ".tar",
    "tar.gz": ".tar.gz",
    "tar.bz2": ".tar.bz2",
}
# tarfile open modes for the tar-based formats.
_TAR_MODES = {"tar": "w", "tar.gz": "w:gz", "tar.bz2": "w:bz2"}

DEFAULT_FORMAT = "zip"


@dataclass
class ArchiveEntry:
    """One file staged for archiving: its source path and name inside the archive."""
    src: str      # absolute path on disk
    arcname: str  # path stored inside the archive (always forward-slashed)
    size: int


def human_size(n: int) -> str:
    """Converts a byte count into a human-readable string (e.g., 1.5 GB)."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def _timestamp() -> str:
    """Returns a filesystem-safe timestamp like 20260705_183000."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _matches(patterns: List[str], arcname: str) -> bool:
    """
    True if any glob pattern matches the arcname, its basename, or any of its
    path components. Lets a single pattern exclude files (``*.log``) or whole
    folders (``__pycache__``, ``node_modules``).
    """
    if not patterns:
        return False
    parts = arcname.split("/")
    candidates = [arcname, parts[-1]] + parts[:-1]
    return any(fnmatch.fnmatch(c, pat) for pat in patterns for c in candidates)


def _is_hidden(rel: str) -> bool:
    """True if any component of the path (relative to a source root) is a dotfile."""
    return any(part.startswith(".") for part in rel.split("/") if part)


def _iter_source_files(source: str):
    """
    Yields (absolute_path, arcname) for every regular file under `source`.

    A file source yields itself, rooted at its own name; a directory source is
    walked recursively and each file is rooted under the directory's name, so
    extracting the archive recreates the original folder. Symlinks are skipped.
    """
    source = os.path.abspath(source)
    root_name = os.path.basename(source.rstrip(os.sep)) or source

    if os.path.isfile(source):
        yield source, root_name
        return

    for root, dirs, files in os.walk(source):
        dirs.sort()
        for name in sorted(files):
            fp = os.path.join(root, name)
            if os.path.islink(fp):
                continue
            rel = os.path.relpath(fp, source).replace(os.sep, "/")
            yield fp, f"{root_name}/{rel}"


def _unique_arcname(arcname: str, seen: set) -> str:
    """Disambiguates an arcname if two sources would collide, adding _1, _2…"""
    if arcname not in seen:
        return arcname
    base, ext = os.path.splitext(arcname)
    i = 1
    while f"{base}_{i}{ext}" in seen:
        i += 1
    return f"{base}_{i}{ext}"


def collect_entries(
    sources: List[str],
    exclude: Optional[List[str]] = None,
    include_hidden: bool = False,
) -> List[ArchiveEntry]:
    """
    Gathers the files to archive from one or more source paths, applying the
    exclude patterns and (unless include_hidden) skipping dotfiles.
    """
    exclude = exclude or []
    entries: List[ArchiveEntry] = []
    seen: set = set()

    for source in sources:
        root_name = os.path.basename(os.path.abspath(source).rstrip(os.sep))
        for fp, arcname in _iter_source_files(source):
            # `rel` is the part below the source root, used for the hidden check
            # so that archiving a hidden folder itself still works.
            rel = arcname[len(root_name) + 1:] if arcname.startswith(root_name + "/") else ""
            if not include_hidden and rel and _is_hidden(rel):
                continue
            if _matches(exclude, arcname):
                continue
            arcname = _unique_arcname(arcname, seen)
            seen.add(arcname)
            try:
                size = os.path.getsize(fp)
            except OSError:
                continue
            entries.append(ArchiveEntry(fp, arcname, size))

    entries.sort(key=lambda e: e.arcname)
    return entries


def _ensure_extension(output: str, fmt: str) -> str:
    """Appends the format's extension to `output` if it is missing."""
    ext = ARCHIVE_FORMATS[fmt]
    return output if output.lower().endswith(ext) else output + ext


def _default_output(sources: List[str], fmt: str) -> str:
    """Builds a timestamped default archive name from the first source."""
    base = os.path.basename(os.path.abspath(sources[0]).rstrip(os.sep)) or "archive"
    return f"{base}_{_timestamp()}{ARCHIVE_FORMATS[fmt]}"


def create_archive(entries: List[ArchiveEntry], output: str, fmt: str) -> None:
    """Writes the staged entries into a zip or tar archive at `output`."""
    if fmt == "zip":
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for e in entries:
                zf.write(e.src, e.arcname)
    else:
        with tarfile.open(output, _TAR_MODES[fmt]) as tf:
            for e in entries:
                tf.add(e.src, arcname=e.arcname, recursive=False)


def _detect_format(path: str) -> Optional[str]:
    """Returns 'zip' or 'tar' for an existing archive, or None if unrecognized."""
    if zipfile.is_zipfile(path):
        return "zip"
    if tarfile.is_tarfile(path):
        return "tar"
    return None


def list_archive(archive_path: str) -> List[Tuple[str, int]]:
    """Returns (name, size) for every regular file inside an archive."""
    kind = _detect_format(archive_path)
    if kind == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            return [(i.filename, i.file_size) for i in zf.infolist() if not i.is_dir()]
    if kind == "tar":
        with tarfile.open(archive_path) as tf:
            return [(m.name, m.size) for m in tf.getmembers() if m.isfile()]
    raise ValueError("not a recognized zip or tar archive")


def _is_within(base: str, target: str) -> bool:
    """True if `target` resolves to a path inside `base` (blocks Zip Slip)."""
    base = os.path.abspath(base)
    target = os.path.abspath(target)
    return target == base or target.startswith(base + os.sep)


def _write_zip_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, target: str) -> None:
    with zf.open(info) as src, open(target, "wb") as out:
        shutil.copyfileobj(src, out)


def _write_tar_member(tf: tarfile.TarFile, member: tarfile.TarInfo, target: str) -> None:
    src = tf.extractfile(member)
    if src is None:
        return
    with src, open(target, "wb") as out:
        shutil.copyfileobj(src, out)


def extract_archive(
    archive_path: str,
    dest: str,
    overwrite: bool = False,
    dry_run: bool = False,
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Extracts an archive into `dest`, returning (written, skipped) where each
    skipped entry is (name, reason). Guards against path traversal, refuses to
    follow archived symlinks, and (unless overwrite) leaves existing files
    untouched. In dry_run mode nothing is written to disk.
    """
    kind = _detect_format(archive_path)
    if kind is None:
        raise ValueError("not a recognized zip or tar archive")

    written: List[str] = []
    skipped: List[Tuple[str, str]] = []

    def _plan(name: str, is_dir: bool, extract_fn: Callable[[str], None]) -> None:
        target = os.path.normpath(os.path.join(dest, name))
        if not _is_within(dest, target):
            skipped.append((name, "unsafe path outside destination"))
            return
        if is_dir:
            if not dry_run:
                os.makedirs(target, exist_ok=True)
            return
        if os.path.exists(target) and not overwrite:
            skipped.append((name, "already exists"))
            return
        if not dry_run:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            extract_fn(target)
        written.append(name)

    if kind == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            for info in zf.infolist():
                _plan(info.filename, info.is_dir(), lambda t, i=info: _write_zip_member(zf, i, t))
    else:
        with tarfile.open(archive_path) as tf:
            for m in tf.getmembers():
                if not (m.isfile() or m.isdir()):
                    skipped.append((m.name, "special member (link/device)"))
                    continue
                _plan(m.name, m.isdir(), lambda t, mm=m: _write_tar_member(tf, mm, t))

    return written, skipped


def _print_entries(title: str, rows: List[Tuple[str, int]], limit: int = 30) -> None:
    """Renders archive contents as a Rich table."""
    table = Table(title=title, show_lines=False, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Size", justify="right", style="yellow")
    table.add_column("Name", overflow="fold")
    for idx, (name, size) in enumerate(rows[:limit], 1):
        table.add_row(str(idx), human_size(size), name)
    console.print(table)
    if len(rows) > limit:
        console.print(f"[dim]... and {len(rows) - limit} more (hidden).[/dim]")


def _run_create(
    sources: List[str],
    output: Optional[str],
    fmt: str,
    exclude: Optional[List[str]],
    include_hidden: bool,
    apply: bool,
) -> bool:
    missing = [s for s in sources if not os.path.exists(s)]
    if missing:
        print_error(f"These source paths do not exist: {', '.join(missing)}")
        return False

    fmt = fmt if fmt in ARCHIVE_FORMATS else DEFAULT_FORMAT
    print_step(f"Collecting files from {len(sources)} source(s)…")
    entries = collect_entries(sources, exclude=exclude, include_hidden=include_hidden)
    if not entries:
        print_warning("No files matched — nothing to archive.")
        return False

    output = _ensure_extension(output or _default_output(sources, fmt), fmt)
    total = sum(e.size for e in entries)

    _print_entries("Files to archive", [(e.arcname, e.size) for e in entries])
    console.print(
        f"\n[bold]{len(entries)}[/bold] file(s), [bold yellow]{human_size(total)}[/bold yellow] "
        f"→ [bold cyan]{output}[/bold cyan] ([dim]{fmt}[/dim])"
    )

    if not apply:
        print_warning("Dry-run: no archive was written. Re-run with --apply to create it.")
        return True

    try:
        create_archive(entries, output, fmt)
    except Exception as e:
        print_error(f"Failed to create archive: {e}")
        return False

    packed = os.path.getsize(output) if os.path.exists(output) else 0
    ratio = f" ({packed / total * 100:.0f}% of original)" if total and packed < total else ""
    print_success(f"Archive created: {output} — {human_size(packed)}{ratio}")
    return True


def _run_list(archive: str) -> bool:
    if not os.path.isfile(archive):
        print_error(f"Archive '{archive}' does not exist.")
        return False
    try:
        rows = list_archive(archive)
    except ValueError as e:
        print_error(str(e))
        return False
    if not rows:
        print_warning("The archive contains no files.")
        return True
    rows.sort(key=lambda r: r[0])
    _print_entries(f"Contents of {os.path.basename(archive)}", rows)
    total = sum(size for _, size in rows)
    console.print(
        f"\n[bold]{len(rows)}[/bold] file(s), [bold yellow]{human_size(total)}[/bold yellow] uncompressed."
    )
    return True


def _run_extract(archive: str, dest: Optional[str], overwrite: bool, apply: bool) -> bool:
    if not os.path.isfile(archive):
        print_error(f"Archive '{archive}' does not exist.")
        return False
    dest = dest or os.path.splitext(os.path.basename(archive))[0]

    verb = "Extracting" if apply else "Previewing"
    print_step(f"{verb} '{os.path.basename(archive)}' → {dest}")
    try:
        written, skipped = extract_archive(archive, dest, overwrite=overwrite, dry_run=not apply)
    except ValueError as e:
        print_error(str(e))
        return False

    for name in written[:30]:
        console.print(f"  [green]✓[/green] {name}")
    if len(written) > 30:
        console.print(f"[dim]... and {len(written) - 30} more.[/dim]")
    for name, reason in skipped:
        print_warning(f"{name}: {reason}")

    if not apply:
        print_warning(
            f"Dry-run: {len(written)} file(s) would be extracted. Re-run with --apply to extract."
        )
        return True

    print_success(f"Extracted {len(written)} file(s) into '{dest}'.")
    return len(written) > 0


def run_archiver(
    action: str,
    sources: Optional[List[str]] = None,
    archive: Optional[str] = None,
    output: Optional[str] = None,
    fmt: str = DEFAULT_FORMAT,
    exclude: Optional[List[str]] = None,
    include_hidden: bool = False,
    dest: Optional[str] = None,
    apply: bool = False,
    overwrite: bool = False,
) -> bool:
    """
    Single entry point shared by the CLI and the interactive menu.

    action:
        "create"  — bundle `sources` into `output` (dry-run unless apply).
        "list"    — print the contents of `archive`.
        "extract" — unpack `archive` into `dest` (dry-run unless apply).
    """
    if action == "create":
        if not sources:
            print_error("At least one source file or folder is required.")
            return False
        return _run_create(sources, output, fmt, exclude, include_hidden, apply)
    if action == "list":
        if not archive:
            print_error("An archive path is required.")
            return False
        return _run_list(archive)
    if action == "extract":
        if not archive:
            print_error("An archive path is required.")
            return False
        return _run_extract(archive, dest, overwrite, apply)

    print_error(f"Unknown action: '{action}'. Use create, list, or extract.")
    return False


def main() -> None:
    """CLI entry point for the Backup / Archiver."""
    parser = argparse.ArgumentParser(
        description="Backup / Archiver: bundle files into a zip/tar archive, list it, or extract it."
    )
    sub = parser.add_subparsers(dest="action", required=True)

    p_create = sub.add_parser("create", help="Create an archive from files/folders (dry-run by default).")
    p_create.add_argument("sources", nargs="+", help="Files and/or folders to archive.")
    p_create.add_argument("-o", "--output", help="Output archive path (default: <source>_<timestamp>).")
    p_create.add_argument(
        "-f", "--format", default=DEFAULT_FORMAT, choices=list(ARCHIVE_FORMATS),
        help=f"Archive format (default: {DEFAULT_FORMAT}).",
    )
    p_create.add_argument(
        "-x", "--exclude", nargs="*", default=[],
        help="Glob patterns to exclude (e.g. '*.log' '__pycache__').",
    )
    p_create.add_argument("--hidden", action="store_true", help="Include hidden dotfiles.")
    p_create.add_argument("--apply", action="store_true", help="Actually write the archive (defaults to dry-run).")

    p_list = sub.add_parser("list", help="List the contents of an archive.")
    p_list.add_argument("archive", help="Archive file to inspect.")

    p_extract = sub.add_parser("extract", help="Extract an archive (dry-run by default).")
    p_extract.add_argument("archive", help="Archive file to extract.")
    p_extract.add_argument("-d", "--dest", help="Destination folder (default: archive name).")
    p_extract.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    p_extract.add_argument("--apply", action="store_true", help="Actually extract (defaults to dry-run).")

    args = parser.parse_args()

    ok = run_archiver(
        action=args.action,
        sources=getattr(args, "sources", None),
        archive=getattr(args, "archive", None),
        output=getattr(args, "output", None),
        fmt=getattr(args, "format", DEFAULT_FORMAT),
        exclude=getattr(args, "exclude", None),
        include_hidden=getattr(args, "hidden", False),
        dest=getattr(args, "dest", None),
        apply=getattr(args, "apply", False),
        overwrite=getattr(args, "overwrite", False),
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
